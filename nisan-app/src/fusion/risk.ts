/**
 * Puts the sources together. Deliberately simple, explainable rules:
 * hazard (what water is doing or about to do) shifted by exposure (how low the ground is).
 */
import { CATALOG } from "../adapters/catalog";
import { RISK_ORDER, type LonLat, type PointSample, type RiskLevel, type Signal, type SourceId } from "../adapters/types";
import type { PointResponse } from "../data/api";
import { data } from "../data/store";
import places from "../data/places.json";
import { distanceKm, level, nearest, peakRatio, rain72, THRESHOLDS, wetnessAt, type PlaceWeather } from "./forecast";

export interface PlaceDef { id: string; name: string; at: LonLat; radiusKm: number; kind: string }
export const PLACES = places.places as PlaceDef[];
export const GAUGES = places.gauges as { id: string; name: string; at: LonLat; places: string[] }[];

export const HAND = {
  1: { label: "0–1 m above the river", exposure: "emergency" as RiskLevel, plain: "barely above the nearest stream; it floods first" },
  2: { label: "1–5 m above the river", exposure: "warning" as RiskLevel, plain: "low ground near drainage; it floods in bigger events" },
  3: { label: "5–15 m above the river", exposure: "watch" as RiskLevel, plain: "raised ground; it floods only in extreme events" },
  4: { label: "over 15 m above the river", exposure: "normal" as RiskLevel, plain: "well above local drainage" },
} as Record<number, { label: string; exposure: RiskLevel; plain: string }>;

const maxLevel = (...l: RiskLevel[]) => l.reduce((a, b) => (RISK_ORDER.indexOf(b) > RISK_ORDER.indexOf(a) ? b : a), "normal" as RiskLevel);
const shift = (l: RiskLevel, by: number): RiskLevel => RISK_ORDER[Math.max(0, Math.min(3, RISK_ORDER.indexOf(l) + by))];
const rank = (l: RiskLevel) => RISK_ORDER.indexOf(l);

export interface Reason { source: SourceId | "fusion"; level: RiskLevel; text: string }
export interface ZoneRisk {
  place: PlaceDef;
  level: RiskLevel;
  previous: RiskLevel;
  lowGround: number;
  reasons: Reason[];
}

/** Latest SMAP root-zone wetness at or before t, if values exist and are recent. */
function smapWetness(t: Date): { v: number; at: Date } | null {
  const s = data.series["smap-l4"];
  const w = s?.rootzone_wetness as (number | null)[] | undefined;
  if (!s || !w) return null;
  let out: { v: number; at: Date } | null = null;
  s.t.forEach((ts, i) => { const d = new Date(ts); if (d <= t && w[i] != null && t.getTime() - d.getTime() < 5 * 864e5) out = { v: w[i] as number, at: d }; });
  return out;
}

/** Everything the hazard model looks at for one place or point. */
export interface HazardInput {
  rivers: { name: string; ratio: number; q: number; at: Date }[];
  rain72: number | null;
  wetness: { v: number; smap: boolean } | null;
  water: { share: number; usual: number } | null;
}

/** How much wet soil lowers the rain thresholds: saturated ground turns more of the rain into runoff. */
export function soilFactor(wet: number | null): number {
  if (wet == null) return 1;
  return wet >= THRESHOLDS.wetness.warning ? 0.5 : wet >= THRESHOLDS.wetness.watch ? 0.75 : 1;
}

/**
 * The one hazard model, used for zones, points, popups, the brief and the CSV.
 * Drivers (river flow, rain, water seen by radar) each give a level. Soil saturation is not a driver
 * on its own: wet ground lowers the rain thresholds. When two or more drivers are above normal
 * they confirm each other and the hazard goes up one step.
 */
export function fuseHazard(inp: HazardInput): { hazard: RiskLevel; reasons: Reason[] } {
  const reasons: Reason[] = [];
  const drivers: RiskLevel[] = [];
  const day = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

  if (inp.rivers.length) {
    const lv = inp.rivers.map((r) => {
      const l = level(r.ratio, THRESHOLDS.dischargeRatio);
      reasons.push({ source: "forecast", level: l, text: `${r.name}: peak ${r.ratio.toFixed(1)}× its usual flow (${Math.round(r.q)} m³/s) on ${day(r.at)}` });
      return l;
    });
    drivers.push(maxLevel(...lv));
  }

  const wet = inp.wetness?.v ?? null;
  const f = soilFactor(wet);
  if (inp.rain72 != null) {
    const l = level(inp.rain72 / f, THRESHOLDS.rain72h);
    const cut = f < 1 ? ` (on wet soil, watch starts at ${Math.round(THRESHOLDS.rain72h.watch * f)} mm instead of ${THRESHOLDS.rain72h.watch})` : "";
    reasons.push({ source: "forecast", level: l, text: `${Math.round(inp.rain72)} mm of rain forecast in the next 72 hours${cut}` });
    drivers.push(l);
  }
  if (inp.wetness) {
    const say = f === 0.5 ? ": saturated, new rain will mostly run off" : f < 1 ? ": wet, heavy rain will pond in low spots" : ": can still soak up rain";
    reasons.push({ source: inp.wetness.smap ? "smap-l4" : "forecast", level: "normal", text: `Soil ${Math.round(inp.wetness.v * 100)} % saturated (${inp.wetness.smap ? "SMAP satellite" : "weather model"})${say}` });
  }

  if (inp.water) {
    const diff = inp.water.share - inp.water.usual;
    const l: RiskLevel = diff >= THRESHOLDS.localWaterShare.warning ? "warning" : diff >= THRESHOLDS.localWaterShare.watch ? "watch" : "normal";
    reasons.push({ source: "opera-dswx-s1", level: l, text: `Water covers ${Math.round(inp.water.share * 100)} % of the area on the last radar pass (usually ${Math.round(inp.water.usual * 100)} %)` });
    drivers.push(l);
  }

  let hazard = maxLevel(...drivers);
  const active = drivers.filter((d) => d !== "normal").length;
  if (active >= 2 && hazard !== "emergency") {
    hazard = shift(hazard, 1);
    reasons.push({ source: "fusion", level: hazard, text: `${active} independent signals are above normal at once, so the level is raised one step` });
  }
  return { hazard, reasons };
}

function wetnessInput(t: Date, w: PlaceWeather | undefined): HazardInput["wetness"] {
  const smap = smapWetness(t);
  if (smap) return { v: smap.v, smap: true };
  const m = w ? wetnessAt(w, t) : null;
  return m == null ? null : { v: m, smap: false };
}

function zoneInput(place: PlaceDef, t: Date): HazardInput {
  const f = data.forecast;
  const rivers: HazardInput["rivers"] = [];
  let rain: number | null = null;
  let w: PlaceWeather | undefined;
  if (f) {
    for (const g of f.gauges.filter((x) => GAUGES.find((y) => y.id === x.id)?.places.includes(place.id))) {
      const p = peakRatio(g, t);
      if (p) rivers.push({ name: g.name, ratio: p.ratio, q: p.q, at: p.at });
    }
    w = f.weather.find((x) => x.id === place.id);
    if (w) rain = rain72(w, t);
  }
  let water: HazardInput["water"] = null;
  const stat = data.places?.places.find((p) => p.id === place.id)?.water["opera-dswx-s1"];
  if (stat) {
    const upto = stat.filter((s) => new Date(s.t) <= t && s.share != null);
    const last = upto.at(-1);
    const prior = upto.slice(0, -1).map((s) => s.share as number).sort((a, b) => a - b);
    if (last && prior.length >= 3) water = { share: last.share as number, usual: prior[Math.floor(prior.length / 2)] };
  }
  return { rivers, rain72: rain, wetness: f ? wetnessInput(t, w) : null, water };
}

/** Zone level: fused hazard, lowered one step where under 15 % of the zone is low ground. */
export function zoneRisk(place: PlaceDef, t: Date): ZoneRisk {
  const shares = data.places?.places.find((p) => p.id === place.id)?.shares ?? {};
  const lowGround = (shares["1"] ?? 0) + (shares["2"] ?? 0);
  const by = lowGround >= 0.15 || !data.places ? 0 : -1;
  const at = (d: Date) => { const h = fuseHazard(zoneInput(place, d)); return { ...h, level: h.hazard === "normal" ? "normal" as RiskLevel : shift(h.hazard, by) }; };
  const now = at(t), before = at(new Date(t.getTime() - 24 * 3600_000));
  const reasons = [...now.reasons];
  if (data.places) reasons.push({ source: "dem-hand", level: "normal", text: `${Math.round(lowGround * 100)} % of the area is low ground (within 5 m of drainage)${by < 0 && now.hazard !== "normal" ? ", so the level is lowered one step" : ""}` });
  return { place, level: now.level, previous: before.level, lowGround, reasons: reasons.sort((a, b) => rank(b.level) - rank(a.level)) };
}

export function zoneRisks(t: Date): ZoneRisk[] {
  return PLACES.map((p) => zoneRisk(p, t)).sort((a, b) => rank(b.level) - rank(a.level));
}

export function allSignals(t: Date): Signal[] {
  const out: Signal[] = [];
  const f = data.forecast;
  if (f) {
    for (const g of f.gauges) {
      const p = peakRatio(g, t);
      if (p) out.push({ source: "forecast", level: level(p.ratio, THRESHOLDS.dischargeRatio), asOf: t, peak: p.at, title: `${g.name}: ${p.ratio.toFixed(1)}× usual flow`, detail: `Forecast peak ${Math.round(p.q)} m³/s on ${p.at.toDateString()}; usually about ${Math.round(p.clim)} m³/s for this date (GloFAS 2006–2025).` });
    }
    for (const w of f.weather) {
      const r = rain72(w, t);
      const wet = wetnessInput(t, w);
      const l = level(r / soilFactor(wet?.v ?? null), THRESHOLDS.rain72h);
      if (l !== "normal") out.push({ source: "forecast", level: l, asOf: t, title: `${PLACES.find((p) => p.id === w.id)?.name}: ${Math.round(r)} mm of rain in 72 hours`, detail: `ECMWF forecast via Open-Meteo${wet ? `, falling on soil ${Math.round(wet.v * 100)} % saturated` : ""}.` });
    }
  }
  const passes = (data.passes["opera-dswx-s1"] ?? []).filter((p) => p.observed_fraction >= 0.5 && new Date(p.t) <= t);
  if (passes.length >= 4) {
    const last = passes.at(-1)!;
    const prior = passes.slice(0, -1).map((p) => p.water_km2).sort((a, b) => a - b);
    const med = prior[Math.floor(prior.length / 2)];
    const ch = med > 0 ? (last.water_km2 - med) / med : 0;
    out.push({ source: "opera-dswx-s1", level: level(ch, THRESHOLDS.basinWater), asOf: new Date(last.t), title: `Surface water ${ch >= 0 ? "+" : ""}${Math.round(ch * 100)} % vs. the recent median`, detail: `${Math.round(last.water_km2)} km² of inland water on ${new Date(last.t).toDateString()} (median of ${prior.length} earlier passes: ${Math.round(med)} km²; ${Math.round(last.observed_fraction * 100)} % of the area observed).` });
  }
  return out.sort((a, b) => rank(b.level) - rank(a.level));
}

export interface PlaceAnswer {
  level: RiskLevel;
  headline: string;
  reasons: string[];
  samples: PointSample[];
  history: { t: Date; code: number }[];
  handClass: number | null;
  handM: number | null;
  elevation: number | null;
  wetShare: number | null;
  /** Set when the answer is a zone verdict. */
  zone?: string;
}

const MATRIX: Record<number, (h: RiskLevel) => RiskLevel> = {
  1: (h) => shift(h, 1), 2: (h) => h, 3: (h) => (h === "normal" ? h : shift(h, -1)), 4: (h) => (h === "emergency" ? "watch" : "normal"),
};

/**
 * The answer for a point. When the point is a named zone, the zone's verdict is the answer, so the map popup,
 * the zone list and the place card always agree; the spot's own terrain is added as detail.
 */
export function answerFor(at: LonLat, t: Date, pt: PointResponse | null, zone?: ZoneRisk): PlaceAnswer {
  const samples: PointSample[] = [];
  const cls = pt?.terrain?.cls ?? null;
  const handM = pt?.terrain?.hand_m ?? null;
  if (cls && HAND[cls]) {
    samples.push({ source: "dem-hand", label: "Height above the nearest stream", value: handM, unit: "m", level: HAND[cls].exposure, reading: `This spot is about ${handM?.toFixed(1)} m above the nearest stream or river: ${HAND[cls].plain}.` });
    if (pt?.terrain?.elevation_m != null) samples.push({ source: "dem-hand", label: "Ground elevation", value: pt.terrain.elevation_m, unit: "m", reading: `About ${Math.round(pt.terrain.elevation_m)} m above sea level (surface height; it may include roofs or trees).` });
  }
  const hist = (pt?.water["opera-dswx-s1"] ?? []).filter((h) => new Date(h.t) <= t).map((h) => ({ t: new Date(h.t), code: h.code }));
  const seen = hist.filter((h) => h.code !== 255);
  const wet = seen.filter((h) => h.code >= 1 && h.code <= 3);
  const share = seen.length ? wet.length / seen.length : null;
  const last = seen.at(-1);
  const words = ["dry", "open water", "partly flooded", "water under vegetation"];
  if (last) {
    samples.push({ source: "opera-dswx-s1", label: "Last clear radar look", value: words[last.code] ?? "unknown", time: last.t, level: last.code === 0 ? "normal" : (share ?? 0) < 0.3 ? "warning" : "watch", reading: `On ${last.t.toLocaleDateString("en-US", { month: "short", day: "numeric" })} the satellite saw ${words[last.code]} here.` });
    samples.push({ source: "opera-dswx-s1", label: "Standing-water history", value: Math.round((share ?? 0) * 100), unit: "% of looks", reading: `Water was seen here in ${wet.length} of ${seen.length} satellite looks since ${seen[0].t.toLocaleDateString("en-US", { month: "short", day: "numeric" })}.${(share ?? 0) >= 0.6 ? " It is usually wet: wetland, lagoon or river." : (share ?? 0) > 0 ? " It floods some of the time." : ""}` });
  }
  const f = data.forecast;
  if (f) {
    const g = nearest(f.gauges, (x) => x.at, at);
    const p = g && peakRatio(g, t);
    if (g && p) samples.push({ source: "forecast", label: `${g.name}: next 10 days`, value: Math.round(p.q), unit: "m³/s", time: p.at, level: level(p.ratio, THRESHOLDS.dischargeRatio), reading: p.ratio >= 1.5 ? `The river is forecast to run ${p.ratio.toFixed(1)}× its usual flow around ${p.at.toLocaleDateString("en-US", { month: "short", day: "numeric" })}.` : `The river is forecast to stay near its usual level (peak ${p.ratio.toFixed(1)}× usual).` });
    const w: PlaceWeather | undefined = nearest(f.weather, (x) => PLACES.find((p) => p.id === x.id)!.at, at);
    if (w) {
      const r = rain72(w, t);
      const sf = soilFactor(wetnessInput(t, w)?.v ?? null);
      samples.push({ source: "forecast", label: "Rain in the next 72 hours", value: Math.round(r), unit: "mm", level: level(r / sf, THRESHOLDS.rain72h), reading: r < 5 ? "Little or no rain is expected in the next three days." : `About ${Math.round(r)} mm of rain is expected in the next three days.` });
      const smap = smapWetness(t);
      const wetNow = smap?.v ?? wetnessAt(w, t);
      if (wetNow != null) samples.push({ source: smap ? "smap-l4" : "forecast", label: `Soil saturation (${smap ? "SMAP" : "model"})`, value: Math.round(wetNow * 100), unit: "%", reading: wetNow >= 0.85 ? "The ground is close to saturated: new rain will mostly run off and pool." : wetNow >= 0.75 ? "The ground is wet; heavy rain will pond in low spots." : "The ground can still soak up some rain." });
    }
  }
  const w = f ? nearest(f.weather, (x) => PLACES.find((p) => p.id === x.id)!.at, at) : undefined;
  const g = f ? nearest(f.gauges, (x) => x.at, at) : undefined;
  const pk = g && peakRatio(g, t);
  const fused = fuseHazard({
    rivers: g && pk ? [{ name: g.name, ratio: pk.ratio, q: pk.q, at: pk.at }] : [],
    rain72: w ? rain72(w, t) : null,
    wetness: f ? wetnessInput(t, w) : null,
    water: null,
  });
  let lv = cls && MATRIX[cls] ? MATRIX[cls](fused.hazard) : fused.hazard;
  if (samples.find((s) => s.label === "Last clear radar look")?.level === "warning") lv = maxLevel(lv, "warning");
  const usuallyWet = (share ?? 0) >= 0.6 && seen.length >= 5;
  if (zone) {
    const spot = cls && HAND[cls] ? ` The pin itself is about ${handM?.toFixed(1)} m above the nearest stream (${HAND[cls].plain}); ${Math.round(zone.lowGround * 100)} % of ${zone.place.name} is low ground.` : "";
    const head = zone.level === "emergency" ? `High flood risk in ${zone.place.name} now. Follow your local civil protection instructions.`
      : zone.level === "warning" ? `Flooding is likely in ${zone.place.name} in the coming days. Prepare now.`
      : zone.level === "watch" ? `Some flood risk in ${zone.place.name}. Keep an eye on the forecast.`
      : `No flooding expected in ${zone.place.name} in the next few days.`;
    const reasons = [...zone.reasons.map((r) => r.text + "."), spot.trim()].filter(Boolean);
    return { level: zone.level, headline: head, reasons, samples, history: hist, handClass: cls, handM, elevation: pt?.terrain?.elevation_m ?? null, wetShare: share, zone: zone.place.id };
  }
  const headline = usuallyWet ? "This spot is usually under water: wetland, lagoon or river."
    : lv === "emergency" ? "High flood risk here now. Follow your local civil protection instructions."
    : lv === "warning" ? "Flooding is likely here in the coming days. Prepare now."
    : lv === "watch" ? "Some flood risk here. Keep an eye on the forecast."
    : "No flooding expected here in the next few days.";
  if (fused.reasons.some((r) => r.source === "fusion")) samples.push({ source: "forecast", label: "Signals agreeing", value: fused.reasons.find((r) => r.source === "fusion")!.text, level: fused.hazard, reading: fused.reasons.find((r) => r.source === "fusion")!.text + "." });
  // Strongest signals first, so the card leads with what matters most right now.
  const reasons = samples.filter((s) => s.label !== "Ground elevation").sort((a, b) => rank(b.level ?? "normal") - rank(a.level ?? "normal")).map((s) => s.reading);
  return { level: lv, headline, reasons, samples, history: hist, handClass: cls, handM, elevation: pt?.terrain?.elevation_m ?? null, wetShare: share };
}

export function brief(t: Date, zones: ZoneRisk[], signals: Signal[]): string {
  const top = zones.filter((z) => z.level !== "normal");
  const fmt = (d: Date) => d.toLocaleString("en-US", { timeZone: "America/Mexico_City", dateStyle: "medium", timeStyle: "short" });
  return [
    `NISAN flood brief: lower Coatzacoalcos basin, ${fmt(t)} (Central Mexico time)`,
    "",
    top.length ? `Zones above normal: ${top.map((z) => `${z.place.name} (${z.level.toUpperCase()})`).join(", ")}` : "All zones are normal.",
    ...top.slice(0, 5).map((z) => `- ${z.place.name}: ${z.reasons.filter((r) => r.level !== "normal").map((r) => r.text).join("; ") || z.reasons[0]?.text}`),
    "",
    "Key signals:",
    ...signals.slice(0, 6).map((s) => `- [${s.level.toUpperCase()}] ${s.title}. ${s.detail}`),
    "",
    `Sources: ${Object.values(CATALOG).filter((c) => c.meta.id !== "radarsat").map((c) => c.meta.name).join("; ")}. Thresholds are provisional.`,
  ].join("\n");
}

export { distanceKm };
