/** Panel content for the two views and the settings sheet. Pure string builders plus small wiring functions. */
import { CATALOG, SOURCE_ORDER } from "../adapters/catalog";
import { RISK_ORDER, type LonLat, type RiskLevel, type Signal } from "../adapters/types";
import { data } from "../data/store";
import type { Settings } from "../data/settings";
import { distanceKm, nearest, peakRatio, rain72, THRESHOLDS, wetnessAt } from "../fusion/forecast";
import { brief, HAND, PLACES, type PlaceAnswer, type ZoneRisk } from "../fusion/risk";
import { chart } from "./chart";

export interface Ctx {
  t: Date;
  now: Date;
  settings: Settings;
  selected: { at: LonLat; name?: string } | null;
  answer: PlaceAnswer | null;
  pointLoading: boolean;
  zones: ZoneRisk[];
  signals: Signal[];
  select: (p: LonLat, name?: string) => void;
}

export const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const rank = (l: RiskLevel) => RISK_ORDER.indexOf(l);
const chip = (l: RiskLevel) => `<span class="chip ${l}">${l}</span>`;
const skel = (n = 3) => Array.from({ length: n }, () => `<div class="skel"></div>`).join("");

export function ago(d: Date | string | number | undefined | null, now = new Date()): string {
  if (!d) return "not yet";
  const t = new Date(d).getTime();
  const m = (now.getTime() - t) / 60_000;
  if (m < 1) return "just now";
  if (m < 60) return `${Math.round(m)} min ago`;
  if (m < 48 * 60) return `${Math.floor(m / 60)} h ago`;
  return `${Math.round(m / 1440)} days ago`;
}

export function dataAges(now = new Date()): string {
  const s = data.now?.sources ?? {};
  const rows: Array<[string, string | undefined, number]> = [
    ["River and rain forecast", data.forecast?.raw.updated, 6],
    ["Radar water map", data.now?.water["opera-dswx-s1"]?.t, 72],
    ["Optical water map", data.now?.water["opera-dswx-hls"]?.t, 120],
    ["NISAR pass", s["nisar-gcov"]?.newest, 14 * 24],
    ["SWOT pass", s["swot-raster"]?.newest, 25 * 24],
    ["SMAP soil moisture", s["smap-l4"]?.newest, 72],
  ];
  return `<dl class="ages">${rows.map(([k, d, h]) => {
    const stale = d && (now.getTime() - new Date(d).getTime()) / 3600_000 > h;
    return `<dt>${k}</dt><dd class="${stale ? "stale" : ""}" title="${d ?? ""}">${ago(d, now)}</dd>`;
  }).join("")}</dl>`;
}

function download(name: string, text: string, type = "text/csv") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function csv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  const q = (v: unknown) => { const s = v instanceof Date ? v.toISOString() : String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [keys.join(","), ...rows.map((r) => keys.map((k) => q(r[k])).join(","))].join("\n");
}

/* ───────── Authorities ───────── */

function hydrograph(ctx: Ctx): string {
  const f = data.forecast;
  if (!f) return skel(4);
  const g = [...f.gauges].sort((a, b) => (peakRatio(b, ctx.t)?.ratio ?? 0) - (peakRatio(a, ctx.t)?.ratio ?? 0))[0];
  if (!g) return `<p class="note">No river forecast yet.</p>`;
  const from = new Date(ctx.now.getTime() - 45 * 864e5);
  const idx = g.t.map((t, i) => ({ t, i })).filter((x) => x.t >= from);
  return `<h3>${esc(g.name)}</h3>` + chart([
    { label: "Ensemble range", color: "#7B5EA7", type: "band", points: idx.map(({ t, i }) => ({ t, v: t > ctx.now ? g.q[i] : null })), upper: idx.map(({ t, i }) => (t > ctx.now ? g.qMax[i] : null)) },
    { label: "Usual for the date", color: "#6B7280", points: idx.map(({ t, i }) => ({ t, v: g.clim50[i] })), width: 1.2 },
    { label: "1-in-10 high", color: "#D9622B", points: idx.map(({ t, i }) => ({ t, v: g.clim90[i] })), width: 1 },
    { label: "Discharge", color: "#2F6DB5", points: idx.map(({ t, i }) => ({ t, v: g.q[i] })), dashedAfter: ctx.now, width: 2.2 },
  ], { now: ctx.t, unit: " m³/s", height: 130 }) + `<p class="note">River discharge in m³/s (GloFAS). Dashed is forecast, shaded is the spread of the ensemble. Usual is the 2006–2025 median for the date.</p>`;
}

export function authorities(ctx: Ctx): string {
  const loading = !data.forecast && !data.now;
  if (loading) return `<h2>Zones</h2>${skel(6)}`;
  const above = ctx.zones.filter((z) => z.level !== "normal");
  const rising = ctx.zones.filter((z) => rank(z.level) > rank(z.previous));
  const water = data.passes["opera-dswx-s1"]?.filter((p) => p.observed_fraction >= 0.3).map((p) => ({ t: new Date(p.t), v: Math.round(p.water_km2) })) ?? [];
  return `
    <div class="actions"><button class="btn primary" data-act="copy-brief">Copy brief</button><button class="btn" data-act="zones-csv">Zones CSV</button></div>
    <p class="lead">${rising.length ? `<b>Rising in the last 24 hours:</b> ${rising.map((z) => esc(z.place.name)).join(", ")}.` : above.length ? "No zone has risen in the last 24 hours." : "All zones are normal."}</p>
    <h2>Zones</h2>
    ${ctx.zones.map((z) => `
      <button class="zone" data-place="${z.place.id}">
        <span class="swatch ${z.level}"></span>
        <span class="zone-text"><b>${esc(z.place.name)}</b>${rank(z.level) > rank(z.previous) ? `<span class="rise">up from ${z.previous}</span>` : ""}
          <small>${esc(z.reasons.find((r) => r.level !== "normal")?.text ?? z.reasons[0]?.text ?? "")}</small></span>
        ${chip(z.level)}
      </button>`).join("")}
    <h2>River forecast</h2>
    ${hydrograph(ctx)}
    <h2>Signals</h2>
    ${ctx.signals.length ? ctx.signals.slice(0, 8).map((s) => `<div class="signal ${s.level}"><b>${esc(s.title)}</b><span>${esc(s.detail)}</span></div>`).join("") : `<p class="note">No signals yet.</p>`}
    <h2>Surface water in the basin</h2>
    ${water.length ? chart([{ label: "Inland water area from radar (km²)", color: "#2F6DB5", points: water, width: 2 }], { now: ctx.t, unit: " km²" }) + `<p class="note">${water.length} Sentinel-1 passes with at least 30 % of the basin observed.</p>` : data.passes["opera-dswx-s1"] ? `<p class="note">No passes yet.</p>` : skel(3)}
    <h2>Data freshness</h2>
    ${dataAges(ctx.now)}
    <p class="note">Thresholds are provisional. See Settings, Research tools.</p>`;
}

export function wireAuthorities(root: HTMLElement, ctx: Ctx) {
  root.querySelector('[data-act="copy-brief"]')?.addEventListener("click", async (e) => {
    const text = brief(ctx.t, ctx.zones, ctx.signals);
    try { await navigator.clipboard.writeText(text); (e.target as HTMLElement).textContent = "Copied"; } catch { download("nisan-brief.txt", text, "text/plain"); }
  });
  root.querySelector('[data-act="zones-csv"]')?.addEventListener("click", () => {
    download(`nisan-zones-${ctx.t.toISOString().slice(0, 13)}.csv`, csv(ctx.zones.map((z) => ({
      zone: z.place.name, lon: z.place.at[0], lat: z.place.at[1], level: z.level, level_24h_ago: z.previous, low_ground_share: z.lowGround.toFixed(2),
      reasons: z.reasons.map((r) => `[${r.level}] ${r.text}`).join(" | "), as_of: ctx.t,
    }))));
  });
  root.querySelectorAll<HTMLElement>(".zone").forEach((el) => el.addEventListener("click", () => {
    const p = PLACES.find((x) => x.id === el.dataset.place)!;
    ctx.select(p.at, p.name);
  }));
}

/* ───────── Overview ───────── */

const TODO: Record<RiskLevel, string[]> = {
  normal: ["Nothing to do now. Save the local civil protection number and know your route to higher ground."],
  watch: ["Check this page and local radio daily.", "Clear gutters and drains around your home.", "Keep documents and medicines in a waterproof bag."],
  warning: ["Move valuables, appliances and documents up high.", "Plan where you will go and how. Check on neighbors who need help.", "Charge phones. Keep water and food for three days."],
  emergency: ["Follow civil protection instructions now.", "If told to leave, leave. Switch off power and gas first.", "Never walk or drive through moving water."],
};

function strip(a: PlaceAnswer): string {
  if (!a.history.length) return `<p class="note">No satellite water maps cover this spot yet.</p>`;
  return `<div class="strip" aria-label="Water seen by the satellite, oldest first">${a.history.map((h) => `<i class="${h.code === 255 ? "na" : h.code === 3 ? "veg" : h.code ? "wet" : ""}" title="${h.t.toDateString()}"></i>`).join("")}</div>
    <div class="key"><span><i class="wet"></i>water</span><span><i class="veg"></i>water under plants</span><span><i></i>dry</span><span><i class="na"></i>not seen</span></div>`;
}

function farm(ctx: Ctx, a: PlaceAnswer): string {
  const at = ctx.selected!.at, f = data.forecast;
  const w = f && nearest(f.weather, (x) => PLACES.find((p) => p.id === x.id)!.at, at);
  if (!w) return skel(3);
  const wetNow = wetnessAt(w, ctx.t), r72 = rain72(w, ctx.t);
  const access = wetNow == null ? "unknown" : wetNow >= THRESHOLDS.wetness.warning || r72 >= 50 ? "poor" : wetNow >= THRESHOLDS.wetness.watch ? "limited" : "good";
  const say = { good: "The ground should carry machinery.", limited: "Soft ground: light equipment only, avoid low spots.", poor: "Waterlogged or heavy rain coming: keep machinery off.", unknown: "No soil data." }[access];
  const from = new Date(ctx.now.getTime() - 31 * 864e5);
  const smap = data.series["smap-l4"];
  const smapPts = smap && smap.rootzone_wetness ? smap.t.map((t, i) => ({ t: new Date(t), v: (smap.rootzone_wetness as (number | null)[])[i] == null ? null : Math.round((smap.rootzone_wetness as number[])[i] * 100) })).filter((p) => p.t >= from) : [];
  return `<h2>Farm details</h2>
    <dl class="kv"><dt>Equipment access</dt><dd>${access}</dd><dt>Soil saturation (model)</dt><dd>${wetNow == null ? "n/a" : Math.round(wetNow * 100) + " %"}</dd>
    <dt>Rain, next 72 hours</dt><dd>${Math.round(r72)} mm</dd><dt>Height above drainage</dt><dd>${a.handM != null ? a.handM.toFixed(1) + " m" : "n/a"}</dd>
    <dt>Standing water (radar looks)</dt><dd>${a.wetShare == null ? "n/a" : Math.round(a.wetShare * 100) + " %"}</dd></dl>
    <p class="note">${esc(say)}</p>
    <h3>Soil saturation, past month and 10-day outlook</h3>
    ${chart([
      { label: `Model near ${esc(PLACES.find((p) => p.id === w.id)!.name)}`, color: "#8A6D3B", points: w.h.map((t, i) => ({ t, v: w.wetness[i] == null ? null : Math.round(w.wetness[i]! * 100) })).filter((p) => p.t >= from), dashedAfter: ctx.now, width: 2 },
      ...(smapPts.length ? [{ label: "SMAP root zone (9 km)", color: "#2F6DB5", points: smapPts, width: 2 }] : []),
    ], { now: ctx.t, unit: " %", yMin: 0, yMax: 100, hlines: [{ v: 85, color: "#D9622B", label: "saturated" }, { v: 75, color: "#B7791F", label: "wet" }] })}
    <h3>Daily rain</h3>
    ${chart([{ label: "mm per day (faded bars are forecast)", color: "#2F6DB5", type: "bar", points: w.d.map((t, i) => ({ t, v: w.rainDaily[i] })), dashedAfter: ctx.now }], { now: ctx.t, unit: " mm" })}
    <p class="note">Satellite cells are about 100 m; the soil model is about 9 to 25 km.</p>`;
}

function readings(a: PlaceAnswer, at: LonLat): string {
  return `<h2>Readings at ${at[1].toFixed(5)}, ${at[0].toFixed(5)}</h2>
    <table class="tbl">${a.samples.map((s) => `<tr><td>${esc(s.label)}</td><td>${s.value == null ? "n/a" : esc(String(typeof s.value === "number" ? +s.value.toFixed(2) : s.value))} ${esc(s.unit ?? "")}</td></tr>`).join("")}</table>
    <div class="actions"><button class="btn" data-act="point-csv">Water history CSV</button></div>`;
}

export function overview(ctx: Ctx): string {
  if (!ctx.selected) {
    return `<h2>Check a place</h2>
      <p class="lead">Search an address or tap the map to see the flood risk there.</p>
      <div class="chips">${PLACES.filter((p) => p.kind !== "wetland").map((p) => `<button class="btn" data-place="${p.id}">${esc(p.name)}</button>`).join("")}</div>
      <p class="note">Answers combine terrain height, the river and rain forecast, and recent satellite water maps.
      ${data.now?.water["opera-dswx-s1"] ? `Latest radar water map: ${new Date(data.now.water["opera-dswx-s1"]!.t).toLocaleDateString("en-US", { month: "long", day: "numeric" })}.` : ""}</p>`;
  }
  const name = ctx.selected.name ?? `${ctx.selected.at[1].toFixed(4)}, ${ctx.selected.at[0].toFixed(4)}`;
  const a = ctx.answer;
  if (!a) return `<h2>${esc(name)}</h2>${skel(5)}`;
  return `
    <h2>${esc(name)}</h2>
    <div class="answer ${a.level}">
      ${chip(a.level)}
      <p class="headline">${esc(a.headline)}</p>
      <ul>${a.reasons.slice(0, 3).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    </div>
    <h2>What to do</h2>
    <ul class="todo">${TODO[a.level].map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <h2>Water seen here by satellite</h2>
    ${strip(a)}
    ${ctx.settings.farm ? farm(ctx, a) : ""}
    ${ctx.settings.research ? readings(a, ctx.selected.at) : ""}
    <p class="note">As of ${ctx.t.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}. This is guidance from satellite and model data, not an official warning.</p>`;
}

export function wireOverview(root: HTMLElement, ctx: Ctx) {
  root.querySelectorAll<HTMLElement>("[data-place]").forEach((el) => el.addEventListener("click", () => {
    const p = PLACES.find((x) => x.id === el.dataset.place)!;
    ctx.select(p.at, p.name);
  }));
  root.querySelector('[data-act="point-csv"]')?.addEventListener("click", () => {
    if (!ctx.answer || !ctx.selected) return;
    download(`nisan-water-history-${ctx.selected.at[1].toFixed(4)}_${ctx.selected.at[0].toFixed(4)}.csv`, csv(ctx.answer.history.map((h) => ({ time: h.t, wtr_code: h.code, meaning: ["dry", "open water", "partial", "water under vegetation"][h.code] ?? "not observed" }))));
  });
}

/* ───────── Settings ───────── */

const toggle = (key: string, label: string, hint: string, on: boolean) =>
  `<label class="opt"><input type="checkbox" data-set="${key}" ${on ? "checked" : ""}/><span><b>${label}</b><small>${hint}</small></span></label>`;

export function settingsSheet(s: Settings, now = new Date()): string {
  const src = data.now?.sources ?? {};
  return `
    <header class="sheet-head"><h2>Settings</h2><button class="icon-btn" data-act="close-settings" aria-label="Close settings"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="m3 3 10 10M13 3 3 13" stroke="currentColor" stroke-width="1.8" fill="none"/></svg></button></header>
    <section><h3>Map</h3>
      <div class="seg" role="radiogroup" aria-label="Basemap">${(["light", "dark", "satellite"] as const).map((b) => `<label><input type="radio" name="basemap" value="${b}" ${s.basemap === b ? "checked" : ""}/><span>${b[0].toUpperCase() + b.slice(1)}</span></label>`).join("")}</div>
      ${toggle("water", "Surface water", "Radar water map for the selected time.", s.water)}
      ${toggle("hand", "Flood-prone ground", "Terrain within 5 m of a river or drain.", s.hand)}
    </section>
    <section><h3>Farm details</h3>
      ${toggle("farm", "Soil and rain charts", "Adds equipment access, soil saturation and rain to the place card.", s.farm)}
    </section>
    <section><h3>More layers</h3>
      ${toggle("optical", "Optical water", "Landsat and Sentinel-2 water map. Clouds can block it.", s.optical)}
      ${toggle("nisar", "NISAR radar image", "L-band backscatter. Sees through vegetation.", s.nisar)}
    </section>
    <section><h3>Research tools</h3>
      ${toggle("research", "Sources, methods and exports", "Shows data sources, caveats, thresholds, readings at a point and downloads.", s.research)}
      ${s.research ? research() : ""}
    </section>
    <section><h3>Data</h3>
      <p class="note">Last refreshed ${ago(data.lastRefresh || null, now)}${data.nowStale ? " (showing the saved copy while updating)" : ""}.</p>
      <ul class="statuses">${SOURCE_ORDER.map((id) => { const st = src[id]; return `<li><span class="dot ${st?.state ?? "unavailable"}"></span><span>${esc(CATALOG[id].meta.name)}</span><small>${st?.state ?? "unavailable"}${st?.newest ? `, ${ago(st.newest, now)}` : ""}</small></li>`; }).join("")}</ul>
      <div class="actions"><button class="btn" data-act="refresh">Refresh now</button></div>
      ${Object.keys(data.errors).length ? `<p class="note warn">Some data could not be loaded: ${Object.keys(data.errors).map(esc).join(", ")}. The app keeps working with what it has.</p>` : ""}
      ${data.timings.now ? `<p class="note">First data in ${data.timings["now-cache"] ?? data.timings.now} ms${data.timings["now-cache"] ? " from the saved copy" : ""}; fresh in ${data.timings.now} ms.</p>` : ""}
    </section>`;
}

function research(): string {
  const th = THRESHOLDS;
  const cat = SOURCE_ORDER.map((id) => {
    const { meta: m, contract: c } = CATALOG[id];
    const st = data.now?.sources[id];
    const spec = (x: { path: string; format: string; fields: Record<string, string>; note?: string }) =>
      `<div class="contract"><div><span>path</span> ${esc(x.path)}</div><div><span>format</span> ${esc(x.format)}</div>${Object.entries(x.fields).map(([k, v]) => `<div><span>${esc(k)}</span> ${esc(v)}</div>`).join("")}${x.note ? `<div>${esc(x.note)}</div>` : ""}</div>`;
    return `<details class="src"><summary><span class="dot" style="background:${m.color}"></span>${esc(m.name)}<small>${st?.state ?? "unavailable"}</small></summary>
      <p>${esc(m.answers)}</p><p class="note">${esc(m.sensor)}. ${esc(m.resolution)}, ${esc(m.revisit)}. Login: ${m.auth}.${st?.message ? ` ${esc(st.message)}` : ""}</p>
      <ul>${m.caveats.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="note">${esc(m.citation)}</p>
      ${c.endpoint.length ? `<b>API</b>${c.endpoint.map(spec).join("")}` : ""}<b>Upstream</b>${c.upstream.map(spec).join("")}
      <div class="actions">${data.timelines[id]?.length ? `<button class="btn" data-export="obs" data-src="${id}">${data.timelines[id].length} acquisitions CSV</button>` : ""}${data.series[id] ? `<button class="btn" data-export="series" data-src="${id}">Series CSV</button>` : ""}</div></details>`;
  }).join("");
  return `<div class="research">${cat}
    <h3>Risk thresholds (provisional)</h3>
    <table class="tbl">
      <tr><td>River flow ÷ usual: watch, warning, emergency</td><td>${th.dischargeRatio.watch}, ${th.dischargeRatio.warning}, ${th.dischargeRatio.emergency}×</td></tr>
      <tr><td>Rain in 72 hours</td><td>${th.rain72h.watch}, ${th.rain72h.warning}, ${th.rain72h.emergency} mm</td></tr>
      <tr><td>Soil saturation: watch, warning</td><td>${th.wetness.watch * 100}, ${th.wetness.warning * 100} %</td></tr>
      <tr><td>Basin water vs. median</td><td>+${th.basinWater.watch * 100}, +${th.basinWater.warning * 100}, +${th.basinWater.emergency * 100} %</td></tr>
      ${Object.entries(HAND).map(([k, c]) => `<tr><td>HAND class ${k}: ${esc(c.label)}</td><td>exposure ${c.exposure}</td></tr>`).join("")}
    </table>
    <p class="note">A zone takes its strongest hazard signal, lowered one step where under 15 % of it is low ground. A point takes the hazard shifted by its HAND class.</p></div>`;
}

export function wireSettings(root: HTMLElement, s: Settings, update: (patch: Partial<Settings>) => void, refresh: () => void, close: () => void) {
  root.querySelectorAll<HTMLInputElement>("input[data-set]").forEach((i) => i.addEventListener("change", () => update({ [i.dataset.set!]: i.checked } as Partial<Settings>)));
  root.querySelectorAll<HTMLInputElement>('input[name="basemap"]').forEach((i) => i.addEventListener("change", () => update({ basemap: i.value as Settings["basemap"] })));
  root.querySelector('[data-act="refresh"]')?.addEventListener("click", refresh);
  root.querySelector('[data-act="close-settings"]')?.addEventListener("click", close);
  root.querySelectorAll<HTMLElement>("[data-export]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.src!;
    if (b.dataset.export === "obs") download(`${id}-acquisitions.csv`, csv((data.timelines[id] ?? []).map((o) => ({ id: o.id, time: o.t, tiles: o.tiles.join(" "), processed: o.processed }))));
    else {
      const sr = data.series[id];
      if (!sr) return;
      const keys = Object.keys(sr).filter((k) => Array.isArray(sr[k]) && k !== "t");
      download(`${id}-series.csv`, csv(sr.t.map((t, i) => ({ time: t, ...Object.fromEntries(keys.map((k) => [k, (sr[k] as (number | null)[])[i]])) }))));
    }
  }));
}

export { distanceKm };
