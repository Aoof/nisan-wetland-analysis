/** Typed access to the NISAN API. Every call takes an AbortSignal so stale requests can be cancelled. */
import type { LonLat, SourceId, SourceStatus } from "../adapters/types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface WaterPass {
  id: string;
  t: string;
  observed_fraction: number;
  water_km2: number;
  open_km2: number;
  partial_km2: number;
  veg_km2: number;
}
export interface NowResponse {
  generated: string;
  sources: Partial<Record<SourceId, SourceStatus>>;
  water: Partial<Record<"opera-dswx-s1" | "opera-dswx-hls", WaterPass & { tiles: string; count: number }>>;
  hand: { tiles: string } | null;
  nisar: { id: string; t: string; tiles: string } | null;
  forecastUpdated: string | null;
}
export interface GaugeJson {
  id: string;
  name: string;
  at: LonLat;
  cell: LonLat;
  places: string[];
  days: string[];
  q: (number | null)[];
  qMax: (number | null)[];
  clim50: (number | null)[];
  clim90: (number | null)[];
}
export interface PlaceWeatherJson {
  id: string;
  hours: string[];
  rain: (number | null)[];
  wetness: (number | null)[];
  days: string[];
  rainDaily: (number | null)[];
  rainProb: (number | null)[];
}
export interface ForecastResponse {
  updated: string;
  porosity: number;
  gauges: GaugeJson[];
  places: PlaceWeatherJson[];
}
export interface PlaceStat {
  id: string;
  shares: Record<string, number>;
  water: Record<string, { t: string; seen: number; share: number | null }[]>;
}
export interface PlacesResponse {
  places: PlaceStat[];
  passes: Record<string, number>;
}
export interface TimelineItem {
  id: string;
  t: string;
  tiles: string[];
  processed: boolean;
}
export interface PointResponse {
  terrain: { cls: number; hand_m: number | null; elevation_m: number | null } | null;
  water: Record<string, { t: string; code: number }[]>;
}
export interface SeriesResponse {
  t: string[];
  [k: string]: (number | null)[] | string[] | string;
}

export type Priority = "high" | "low" | "auto";

/** `fresh` always revalidates with the server (an ETag makes that a tiny 304); used for time-critical data. */
export async function getJson<T>(path: string, signal?: AbortSignal, priority: Priority = "auto", fresh = false): Promise<T> {
  const r = await fetch(BASE + path, { signal, priority, cache: fresh ? "no-cache" : "default" } as RequestInit);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  now: (s?: AbortSignal) => getJson<NowResponse>("/api/now", s, "high", true),
  forecast: (s?: AbortSignal) => getJson<ForecastResponse>("/api/forecast", s, "high", true),
  places: (s?: AbortSignal) => getJson<PlacesResponse>("/api/places", s, "low"),
  timeline: (source: string, s?: AbortSignal) => getJson<TimelineItem[]>(`/api/timeline/${source}`, s, "low"),
  passes: (prod: string, s?: AbortSignal) => getJson<WaterPass[]>(`/api/passes/${prod}`, s, "low"),
  series: (source: string, s?: AbortSignal) => getJson<SeriesResponse>(`/api/series/${source}`, s, "low"),
  point: (p: LonLat, s?: AbortSignal) => getJson<PointResponse>(`/api/point?lon=${p[0].toFixed(5)}&lat=${p[1].toFixed(5)}`, s, "high"),
  url: (path: string) => BASE + path,
};
