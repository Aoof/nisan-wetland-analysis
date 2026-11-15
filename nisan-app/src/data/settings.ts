/** Viewer preferences, remembered in this browser only. */
export type View = "overview" | "authorities";
export type Basemap = "light" | "dark" | "satellite";

export interface Settings {
  view: View;
  basemap: Basemap;
  water: boolean;
  hand: boolean;
  optical: boolean;
  nisar: boolean;
  farm: boolean;
  research: boolean;
}

export const DEFAULTS: Settings = { view: "overview", basemap: "light", water: true, hand: true, optical: false, nisar: false, farm: false, research: false };
const KEY = "nisan-settings-v1";

export function loadSettings(): Settings {
  let s: Partial<Settings> = {};
  try { s = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Settings>; } catch { /* blocked storage */ }
  const q = new URLSearchParams(location.search).get("view");
  return { ...DEFAULTS, ...s, ...(q === "authorities" || q === "overview" ? { view: q } : {}) };
}

export function saveSettings(s: Settings): void {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ }
}
