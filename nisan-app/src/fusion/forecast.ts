/** Pure helpers over the forecast JSON. */
import type { ForecastResponse, GaugeJson, PlaceWeatherJson } from "../data/api";
import { type LonLat, type RiskLevel } from "../adapters/types";

export const THRESHOLDS = {
  dischargeRatio: { watch: 1.5, warning: 2, emergency: 3 },
  rain72h: { watch: 50, warning: 100, emergency: 150 },
  wetness: { watch: 0.75, warning: 0.85 },
  basinWater: { watch: 0.15, warning: 0.3, emergency: 0.5 },
  localWaterShare: { watch: 0.07, warning: 0.15 },
};

export function level(v: number, t: { watch: number; warning: number; emergency?: number }): RiskLevel {
  if (t.emergency !== undefined && v >= t.emergency) return "emergency";
  if (v >= t.warning) return "warning";
  if (v >= t.watch) return "watch";
  return "normal";
}

const day = (s: string) => new Date(`${s}T12:00:00Z`);
const hour = (s: string) => new Date(`${s}:00Z`);

export interface Gauge extends GaugeJson { t: Date[] }
export interface PlaceWeather extends PlaceWeatherJson { h: Date[]; d: Date[] }

export function prepare(f: ForecastResponse): { gauges: Gauge[]; weather: PlaceWeather[] } {
  return {
    gauges: f.gauges.map((g) => ({ ...g, t: g.days.map(day) })),
    weather: f.places.map((p) => ({ ...p, h: p.hours.map(hour), d: p.days.map(day) })),
  };
}

const km = (a: LonLat, b: LonLat) => {
  const r = Math.PI / 180, R = 6371;
  const h = Math.sin(((b[1] - a[1]) * r) / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(((b[0] - a[0]) * r) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
export const distanceKm = km;

export function rain72(w: PlaceWeather, from: Date): number {
  let s = 0;
  w.h.forEach((h, i) => { if (h >= from && h.getTime() < from.getTime() + 72 * 3600_000) s += w.rain[i] ?? 0; });
  return s;
}

export function wetnessAt(w: PlaceWeather, t: Date): number | null {
  let v: number | null = null;
  w.h.forEach((h, i) => { if (h <= t && w.wetness[i] != null) v = w.wetness[i]; });
  return v;
}

export function peakRatio(g: Gauge, t: Date, days = 10) {
  let best: { ratio: number; q: number; at: Date; clim: number } | null = null;
  g.t.forEach((d, i) => {
    if (d < t || d.getTime() > t.getTime() + days * 864e5) return;
    const q = g.q[i], c = g.clim50[i];
    if (q == null || !c) return;
    if (!best || q / c > best.ratio) best = { ratio: q / c, q, at: d, clim: c };
  });
  return best as { ratio: number; q: number; at: Date; clim: number } | null;
}

export function nearest<T>(items: T[], at: (x: T) => LonLat, p: LonLat): T | undefined {
  return [...items].sort((a, b) => km(at(a), p) - km(at(b), p))[0];
}
