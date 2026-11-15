/** Shared vocabulary for every NISAN data source. Raw formats are handled by the API; the app only sees these. */

export type BBox = [west: number, south: number, east: number, north: number];
export type LonLat = [lon: number, lat: number];

/** Lower Coatzacoalcos basin, same box as the API. */
export const AOI: { name: string; bbox: BBox } = { name: "coatzacoalcos", bbox: [-94.9, 17.6, -94.0, 18.3] };

export type SourceId =
  | "dem-hand" | "opera-dswx-s1" | "opera-dswx-hls" | "nisar-gcov" | "swot-raster" | "smap-l4" | "radarsat" | "forecast";

/** live: values are current. refreshing: a job is running, showing the last copy. awaiting-data: acquisitions known, values not processed. */
export type SourceState = "live" | "refreshing" | "awaiting-data" | "unavailable" | "error";

export interface SourceStatus {
  state: SourceState;
  message?: string;
  updated_at?: string;
  newest?: string;
  found?: number;
  processed?: number;
}

export interface SourceMeta {
  id: SourceId;
  name: string;
  sensor: string;
  answers: string;
  measures: string[];
  resolution: string;
  revisit: string;
  latency: string;
  auth: "none" | "earthdata" | "eodms";
  caveats: string[];
  citation: string;
  color: string;
}

/** What the API delivers for each source, shown to researchers in Settings. */
export interface InputSpec {
  path: string;
  format: string;
  fields: Record<string, string>;
  note?: string;
}

export interface SourceContract {
  endpoint: InputSpec[];
  upstream: InputSpec[];
}

export type RiskLevel = "normal" | "watch" | "warning" | "emergency";
export const RISK_ORDER: RiskLevel[] = ["normal", "watch", "warning", "emergency"];

export interface Signal {
  source: SourceId;
  level: RiskLevel;
  title: string;
  detail: string;
  asOf: Date;
  peak?: Date;
}

export interface PointSample {
  source: SourceId;
  label: string;
  value: number | string | null;
  unit?: string;
  time?: Date;
  reading: string;
  level?: RiskLevel;
}

export interface TimeSeries {
  source: SourceId;
  id: string;
  label: string;
  unit: string;
  points: { t: Date; v: number | null }[];
}
