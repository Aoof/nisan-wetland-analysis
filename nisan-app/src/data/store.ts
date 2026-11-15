/**
 * App data, loaded fastest-first:
 *   1. last session's cache from IndexedDB, drawn at once
 *   2. /api/now + /api/forecast (small, high priority)
 *   3. everything else when the browser is idle
 * Consumers subscribe to topics and re-render only what changed.
 */
import { SOURCE_ORDER } from "../adapters/catalog";
import { prepare, type Gauge, type PlaceWeather } from "../fusion/forecast";
import { api, type ForecastResponse, type NowResponse, type PlacesResponse, type SeriesResponse, type TimelineItem, type WaterPass } from "./api";
import { restoreCache, swr, whenIdle } from "./client";

export type Topic = "now" | "forecast" | "places" | "timeline" | "passes" | "series" | "status";

export interface Data {
  now: NowResponse | null;
  nowStale: boolean;
  forecast: { raw: ForecastResponse; gauges: Gauge[]; weather: PlaceWeather[] } | null;
  places: PlacesResponse | null;
  timelines: Record<string, TimelineItem[]>;
  passes: Record<string, WaterPass[]>;
  series: Record<string, SeriesResponse | null>;
  errors: Record<string, string>;
  lastRefresh: number;
  /** milliseconds from page start until each stage had data, for the performance readout */
  timings: Record<string, number>;
}

export const data: Data = {
  now: null, nowStale: false, forecast: null, places: null, timelines: {}, passes: {}, series: {}, errors: {}, lastRefresh: 0, timings: {},
};

type Listener = (t: Topic) => void;
const listeners = new Set<Listener>();
export const subscribe = (fn: Listener) => { listeners.add(fn); return () => listeners.delete(fn); };
const emit = (t: Topic) => listeners.forEach((l) => l(t));
const mark = (k: string) => { data.timings[k] ??= Math.round(performance.now()); };

const fail = (k: string) => (e: unknown) => { data.errors[k] = e instanceof Error ? e.message : String(e); emit("status"); };
const ok = (k: string) => { delete data.errors[k]; };

function loadCritical(): Promise<void[]> {
  return Promise.all([
    swr({
      key: ["now"], fetcher: api.now, staleTime: 0, onError: fail("now"),
      onData: (d, m) => { data.now = d; data.nowStale = m.fromCache; ok("now"); data.lastRefresh = m.updatedAt; mark(m.fromCache ? "now-cache" : "now"); emit("now"); },
    }),
    swr({
      key: ["forecast"], fetcher: api.forecast, staleTime: 0, onError: fail("forecast"),
      onData: (d, m) => { data.forecast = { raw: d, ...prepare(d) }; ok("forecast"); mark(m.fromCache ? "forecast-cache" : "forecast"); emit("forecast"); },
    }),
  ]);
}

const wanted = new Set<string>();

/** Timelines and series are fetched on demand; the first screen needs only the radar timeline. */
export function want(source: string): void {
  if (wanted.has(source)) return;
  wanted.add(source);
  if (source === "smap-l4" || source === "swot-raster") {
    swr({ key: ["series", source], fetcher: (s) => api.series(source, s), staleTime: 10 * 60_000, onError: () => { data.series[source] = null; emit("series"); }, onData: (d) => { data.series[source] = d; mark(`series-${source}`); emit("series"); } });
  }
  swr({ key: ["timeline", source], fetcher: (s) => api.timeline(source, s), staleTime: 60_000, onError: fail(`timeline-${source}`), onData: (d) => { data.timelines[source] = d; mark(`timeline-${source}`); emit("timeline"); } });
  if (source === "opera-dswx-s1" || source === "opera-dswx-hls") {
    swr({ key: ["passes", source], fetcher: (s) => api.passes(source, s), staleTime: 5 * 60_000, onError: fail(`passes-${source}`), onData: (d) => { data.passes[source] = d; mark(`passes-${source}`); emit("passes"); } });
  }
}

function loadBackground(): void {
  whenIdle(() => {
    swr({ key: ["places"], fetcher: api.places, staleTime: 5 * 60_000, onError: fail("places"), onData: (d) => { data.places = d; ok("places"); mark("places"); emit("places"); } });
    want("opera-dswx-s1");
    want("smap-l4");
    want("swot-raster");
  });
}

export async function boot(): Promise<void> {
  await restoreCache();
  mark("cache-restored");
  await loadCritical();
  loadBackground();
  // keep fresh: every 10 minutes and whenever the tab becomes visible again
  const refresh = () => { loadCritical(); swr({ key: ["places"], fetcher: api.places, staleTime: 5 * 60_000, onData: (d) => { data.places = d; emit("places"); } }); };
  setInterval(refresh, 10 * 60_000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Date.now() - data.lastRefresh > 5 * 60_000) refresh(); });
}

export function refreshNow(): Promise<void> {
  return loadCritical().then(() => undefined);
}

export const SOURCES = SOURCE_ORDER;
