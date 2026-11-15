import maplibregl from "maplibre-gl";
import "./style.css";
import { CATALOG } from "./adapters/catalog";
import { AOI, RISK_ORDER, type LonLat } from "./adapters/types";
import { api, type PointResponse } from "./data/api";
import { loadSettings, saveSettings, type Settings, type View } from "./data/settings";
import { boot, data, refreshNow, subscribe, want, type Topic } from "./data/store";
import { peakRatio } from "./fusion/forecast";
import { allSignals, answerFor, PLACES, zoneRisk, zoneRisks, type PlaceAnswer, type ZoneRisk } from "./fusion/risk";
import { LEVEL_COLOR, MapView } from "./ui/map";
import * as P from "./ui/panels";
import { Timebar } from "./ui/timebar";

const NOW = new Date();
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const panel = $("panel"), body = $("panelBody"), band = $("band"), legend = $("legend"), sheet = $("settings");

const state = {
  settings: loadSettings(),
  t: NOW,
  selected: null as { at: LonLat; name?: string } | null,
  answer: null as PlaceAnswer | null,
  pointLoading: false,
  point: null as PointResponse | null,
  zones: [] as ZoneRisk[],
  signals: [] as ReturnType<typeof allSignals>,
};

const view = new MapView($("map"), state.settings.basemap, (p) => select(p));
let popup: maplibregl.Popup | null = null;
let pointAbort: AbortController | null = null;

/* ───────── batching: many data events, one repaint per frame ───────── */
const dirty = new Set<string>();
let queued = false;
function schedule(...parts: string[]) {
  parts.forEach((p) => dirty.add(p));
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    const d = new Set(dirty);
    dirty.clear();
    if (d.has("zones")) { state.zones = zoneRisks(state.t); state.signals = allSignals(state.t); }
    if (d.has("answer") && state.selected && !state.pointLoading) state.answer = answerFor(state.selected.at, state.t, state.point, zoneFor(state.selected));
    if (d.has("layers")) drawLayers();
    if (d.has("rows")) setRows();
    if (d.has("band")) renderBand();
    if (d.has("legend")) renderLegend();
    if (d.has("markers")) drawMarkers();
    if (d.has("panel")) renderPanel();
    if (d.has("sheet") && !sheet.hidden) renderSheet();
  });
}

/** A selection made from a zone (list, pin, search) is judged as that zone, so every surface shows the same level. */
function zoneFor(sel: { at: LonLat; name?: string } | null): ZoneRisk | undefined {
  const p = sel?.name ? PLACES.find((x) => x.name === sel.name && x.at[0] === sel.at[0] && x.at[1] === sel.at[1]) : undefined;
  return p ? state.zones.find((z) => z.place.id === p.id) ?? zoneRisk(p, state.t) : undefined;
}

/* ───────── time → which pass to show ───────── */
function passFor(prod: "opera-dswx-s1" | "opera-dswx-hls", t: Date): string | null {
  const tl = data.timelines[prod]?.filter((p) => p.processed);
  if (tl?.length) {
    if (t >= NOW) return tl.at(-1)!.id;
    return tl.filter((p) => new Date(p.t) <= t).at(-1)?.id ?? null;
  }
  const n = data.now?.water[prod];
  return n && t >= new Date(new Date(n.t).getTime() - 1000) ? n.id : n && t >= NOW ? n.id : n?.id ?? null;
}
function nisarFor(t: Date): string | null {
  const tl = data.timelines["nisar-gcov"]?.filter((p) => p.processed);
  if (tl?.length) return (t >= NOW ? tl.at(-1) : tl.filter((p) => new Date(p.t) <= t).at(-1))?.id ?? null;
  return data.now?.nisar?.id ?? null;
}
const abs = (path: string) => location.origin + path;

/* ───────── map layers ───────── */
function drawLayers() {
  const s = state.settings;
  const water = s.water ? passFor("opera-dswx-s1", state.t) : null;
  const optical = s.optical ? passFor("opera-dswx-hls", state.t) : null;
  const nisar = s.nisar ? nisarFor(state.t) : null;
  const r = (path: string, opacity: number, maxzoom = 12) => ({ tiles: abs(path), opacity, maxzoom });
  const go = () => {
    view.setRaster("hand", s.hand && data.now?.hand ? r(data.now.hand.tiles, 0.5, 13) : null);
    view.setRaster("nisar", nisar ? r(`/api/tiles/nisar-gcov/${nisar}/{z}/{x}/{y}.png`, 0.85, 11) : null);
    view.setRaster("optical", optical ? r(`/api/tiles/opera-dswx-hls/${optical}/{z}/{x}/{y}.png`, 0.85) : null);
    view.setRaster("water", water ? r(`/api/tiles/opera-dswx-s1/${water}/{z}/{x}/{y}.png`, 0.9) : null);
  };
  view.ready.then(() => (view.map.isStyleLoaded() ? go() : view.map.once("idle", go)));
  const f = data.forecast;
  view.ready.then(() => view.setGauges(
    f && state.settings.view === "authorities" ? {
      type: "FeatureCollection",
      features: f.gauges.map((g) => {
        // Same quantity the zones use: the forecast peak over the next 10 days, not today's flow.
        const pk = peakRatio(g, state.t);
        return { type: "Feature", geometry: { type: "Point", coordinates: g.cell }, properties: { id: g.id, name: g.name, ratio: pk ? pk.ratio : -1 } };
      }),
    } : null,
    (id, at) => {
      const g = f?.gauges.find((x) => x.id === id);
      const pk = g && peakRatio(g, state.t);
      popup?.remove();
      if (g) popup = new maplibregl.Popup({ maxWidth: "260px" }).setLngLat(at).setHTML(`<b>${P.esc(g.name)}</b>${pk ? `<br>Peak in the next 10 days: ${Math.round(pk.q)} m³/s on ${pk.at.toLocaleDateString("en-US", { month: "short", day: "numeric" })} (${pk.ratio.toFixed(1)}× usual)` : ""}`).addTo(view.map);
    },
  ));
}

function drawMarkers() {
  if (state.settings.view === "authorities") view.zones(state.zones, (z) => select(z.place.at, z.place.name, true));
  else view.clearZones();
}

/* ───────── legend, band, time bar rows ───────── */
function renderLegend() {
  const s = state.settings, items: string[] = [];
  const dot = (c: string, l: string) => `<span><i style="background:${c}"></i>${l}</span>`;
  if (s.water) items.push(dot("#2f6db5", "Open water"), dot("#16a085", "Water under vegetation"));
  if (s.optical) items.push(dot("#7aa6d8", "Optical water"));
  if (s.hand) items.push(dot("#c62828", "Within 1 m of the river"), dot("#d9622b", "1 to 5 m above the river"));
  if (s.nisar) items.push(dot("#6b7280", "NISAR radar image"));
  if (s.view === "authorities") {
    items.push(...(["normal", "watch", "warning", "emergency"] as const).map((l) => dot(LEVEL_COLOR[l], `Zone: ${l}`)));
    items.push(`<span><i class="gauge-key"></i>River gauge: 10-day peak vs. usual flow</span>`);
  }
  legend.innerHTML = items.join("");
}

function renderBand() {
  const show = state.settings.view === "authorities" && !!state.zones.length;
  band.hidden = !show;
  if (!show) return;
  const worst = state.zones[0].level, above = state.zones.filter((z) => z.level !== "normal");
  band.style.setProperty("--lv", LEVEL_COLOR[worst]);
  band.innerHTML = `<span class="lv">${worst}</span><span>${above.length ? above.slice(0, 4).map((z) => P.esc(z.place.name)).join(", ") + (above.length > 4 ? ` and ${above.length - 4} more` : "") : "All zones normal"}</span><span class="clock" id="clock"></span>`;
  tick();
}
function tick() {
  const c = document.getElementById("clock");
  if (c) c.textContent = `Forecast updated ${P.ago(data.forecast?.raw.updated)}. ${new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
}
setInterval(tick, 30_000);

const timebar = new Timebar({ el: $("timebar"), start: new Date(NOW.getTime() - 120 * 864e5), end: new Date(NOW.getTime() + 30 * 864e5), now: NOW, onChange: (t) => { state.t = t; schedule("zones", "answer", "layers", "panel", "band", "markers"); } });
function setRows() {
  const s = state.settings;
  const row = (id: string, label: string, color: string) => ({ label, color, times: (data.timelines[id] ?? []).map((x) => new Date(x.t)) });
  const rows = [row("opera-dswx-s1", "Radar water", CATALOG["opera-dswx-s1"].meta.color)];
  if (s.optical) rows.push(row("opera-dswx-hls", "Optical water", CATALOG["opera-dswx-hls"].meta.color));
  if (s.nisar) rows.push(row("nisar-gcov", "NISAR", CATALOG["nisar-gcov"].meta.color));
  if (s.research) rows.push(row("swot-raster", "SWOT", CATALOG["swot-raster"].meta.color), row("smap-l4", "SMAP", CATALOG["smap-l4"].meta.color));
  timebar.setRows(rows);
}
function wantTimelines() {
  const s = state.settings;
  want("opera-dswx-s1");
  if (s.optical) want("opera-dswx-hls");
  if (s.nisar) want("nisar-gcov");
  if (s.research) { want("swot-raster"); want("smap-l4"); }
}

/* ───────── panel ───────── */
function ctx(): P.Ctx {
  return { t: state.t, now: NOW, settings: state.settings, selected: state.selected, answer: state.answer, pointLoading: state.pointLoading, zones: state.zones, signals: state.signals, select: (p, n) => select(p, n, true) };
}
function renderPanel() {
  const c = ctx();
  const top = body.scrollTop;
  if (state.settings.view === "authorities") { body.innerHTML = P.authorities(c); P.wireAuthorities(body, c); }
  else { body.innerHTML = P.overview(c); P.wireOverview(body, c); }
  body.scrollTop = top;
}

/* ───────── settings sheet ───────── */
function renderSheet() {
  const top = sheet.scrollTop;
  sheet.innerHTML = P.settingsSheet(state.settings);
  P.wireSettings(sheet, state.settings, update, () => refreshNow(), closeSheet);
  sheet.scrollTop = top;
}
function openSheet() { sheet.hidden = false; $("settingsBtn").setAttribute("aria-expanded", "true"); renderSheet(); }
function closeSheet() { sheet.hidden = true; $("settingsBtn").setAttribute("aria-expanded", "false"); }
$("settingsBtn").addEventListener("click", () => (sheet.hidden ? openSheet() : closeSheet()));
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheet.hidden) closeSheet(); });

function update(patch: Partial<Settings>) {
  state.settings = { ...state.settings, ...patch };
  saveSettings(state.settings);
  if (patch.basemap) view.setBasemap(patch.basemap);
  wantTimelines();
  schedule("layers", "rows", "legend", "panel", "sheet");
}

/* ───────── views ───────── */
function setView(v: View, persist = true) {
  state.settings = { ...state.settings, view: v };
  if (persist) saveSettings(state.settings);
  document.body.dataset.view = v;
  document.querySelectorAll<HTMLButtonElement>(".views button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === v)));
  const u = new URL(location.href); u.searchParams.set("view", v); history.replaceState(null, "", u);
  popup?.remove();
  schedule("zones", "layers", "band", "legend", "markers", "panel");
}
document.querySelectorAll<HTMLButtonElement>(".views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view as View)));
$("collapse").addEventListener("click", () => panel.classList.toggle("collapsed"));

/* ───────── selecting a place ───────── */
async function select(at: LonLat, name?: string, fly = false) {
  pointAbort?.abort();
  const ac = (pointAbort = new AbortController());
  state.selected = { at, name };
  state.answer = null;
  state.point = null;
  state.pointLoading = true;
  view.setPin(at);
  if (fly) view.flyTo(at, name && PLACES.some((x) => x.name === name) ? 12 : 14);
  if (state.settings.view === "overview") panel.classList.remove("collapsed");
  schedule("panel");
  try {
    state.point = await api.point(at, ac.signal);
  } catch (e) {
    if (ac.signal.aborted) return;
    state.point = null;
  }
  if (ac.signal.aborted) return;
  state.pointLoading = false;
  state.answer = answerFor(at, state.t, state.point, zoneFor(state.selected));
  if (state.settings.view === "authorities") {
    popup?.remove();
    const a = state.answer;
    popup = new maplibregl.Popup({ maxWidth: "300px" }).setLngLat(at).setHTML(`<b>${P.esc(name ?? `${at[1].toFixed(4)}, ${at[0].toFixed(4)}`)}</b><br><span class="chip ${a.level}">${a.level}</span>${a.zone ? ` <small>zone verdict</small>` : ""}<p style="margin:6px 0 0">${P.esc(a.headline)}</p><ul class="popup-reasons">${a.reasons.slice(0, 3).map((r) => `<li>${P.esc(r)}</li>`).join("")}</ul>`).addTo(view.map);
  }
  schedule("panel");
}

/* ───────── search: coordinates, basin places, then OpenStreetMap (English, bounded to the basin) ───────── */
const norm = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
const results = $("results") as HTMLUListElement;
function showResults(items: Array<{ name: string; sub?: string; at: LonLat }>) {
  results.hidden = !items.length;
  results.innerHTML = items.map((r, i) => `<li tabindex="0" data-i="${i}">${P.esc(r.name)}${r.sub ? `<small>${P.esc(r.sub)}</small>` : ""}</li>`).join("");
  results.querySelectorAll<HTMLLIElement>("li").forEach((li) => {
    const go = () => { const r = items[+li.dataset.i!]; results.hidden = true; select(r.at, r.name, true); };
    li.addEventListener("click", go);
    li.addEventListener("keydown", (e) => e.key === "Enter" && go());
  });
}
$("q").addEventListener("input", (e) => {
  const q = norm((e.target as HTMLInputElement).value.trim());
  showResults(q.length < 2 ? [] : PLACES.filter((p) => norm(p.name).includes(q)).map((p) => ({ name: p.name, sub: "Place in the basin", at: p.at })));
});
$("search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = ($("q") as HTMLInputElement).value.trim();
  const ll = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (ll) { const a = +ll[1], b = +ll[2]; results.hidden = true; return select(Math.abs(a) <= 90 && Math.abs(b) > 90 ? [b, a] : [a, b], undefined, true); }
  const local = PLACES.filter((p) => norm(p.name).includes(norm(q)));
  if (local.length) return showResults(local.map((p) => ({ name: p.name, sub: "Place in the basin", at: p.at })));
  const [w, s, ea, n] = AOI.bbox;
  try {
    const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&bounded=1&viewbox=${w},${n},${ea},${s}&q=${encodeURIComponent(q)}`, { headers: { "Accept-Language": "en" } });
    const j = (await r.json()) as Array<{ display_name: string; lat: string; lon: string }>;
    showResults(j.length ? j.map((x) => ({ name: x.display_name.split(",")[0], sub: x.display_name.split(",").slice(1, 3).join(","), at: [+x.lon, +x.lat] as LonLat })) : [{ name: "No match inside the basin", at: [(w + ea) / 2, (s + n) / 2] }]);
  } catch { showResults([]); }
});
document.addEventListener("click", (e) => { if (!(e.target as HTMLElement).closest(".search")) results.hidden = true; });

/* ───────── data events → repaint only what changed ───────── */
const ROUTES: Record<Topic, string[]> = {
  now: ["layers", "band", "panel", "sheet", "legend"],
  forecast: ["zones", "answer", "layers", "band", "markers", "panel", "sheet"],
  places: ["zones", "band", "markers", "panel"],
  timeline: ["rows", "layers"],
  passes: ["zones", "band", "markers", "panel"],
  series: ["zones", "answer", "panel", "markers", "band"],
  status: ["sheet"],
};
subscribe((t) => schedule(...ROUTES[t]));

/* ───────── start ───────── */
document.body.dataset.view = state.settings.view;
document.querySelectorAll<HTMLButtonElement>(".views button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.settings.view)));
renderLegend();
renderPanel();
wantTimelines();
boot();
Object.assign(window, { nisan: { state, data, view, select, update, setView } });
void RISK_ORDER;
