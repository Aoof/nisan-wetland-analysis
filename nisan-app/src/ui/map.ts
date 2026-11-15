import maplibregl, { type Map as MLMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Basemap } from "../data/settings";
import { AOI, type LonLat, type RiskLevel } from "../adapters/types";
import type { ZoneRisk } from "../fusion/risk";

export const LEVEL_COLOR: Record<RiskLevel, string> = { normal: "#2E7D32", watch: "#B7791F", warning: "#D9622B", emergency: "#C62828" };

const CARTO = "https://basemaps.cartocdn.com/gl/";
const KEY = import.meta.env.CARTO_API_KEY as string | undefined;
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

const SATELLITE: StyleSpecification = {
  version: 8,
  sources: {
    imagery: { type: "raster", tiles: [`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" },
    places: { type: "raster", tiles: [`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 19 },
  },
  layers: [{ id: "imagery", type: "raster", source: "imagery" }, { id: "labels", type: "raster", source: "places" }],
};

const STYLE: Record<Basemap, string | StyleSpecification> = {
  light: `${CARTO}positron-gl-style/style.json`,
  dark: `${CARTO}dark-matter-gl-style/style.json`,
  satellite: SATELLITE,
};

/** Bottom to top: terrain first, radar water on top of everything else. */
const STACK = ["hand", "nisar", "optical", "water"];

interface RasterSpec { tiles: string; opacity: number; maxzoom: number }
interface Slot { n: number; spec: RasterSpec | null; current: string | null }

export class MapView {
  map: MLMap;
  private slots = new Map<string, Slot>();
  private zoneMarkers: maplibregl.Marker[] = [];
  private pin: maplibregl.Marker | null = null;
  private gauges: GeoJSON.FeatureCollection | null = null;
  private onGauge: ((id: string, at: LonLat) => void) | null = null;
  ready: Promise<void>;
  styleKey: Basemap = "light";

  constructor(el: HTMLElement, basemap: Basemap, onClick: (p: LonLat) => void) {
    const [w, s, e, n] = AOI.bbox;
    this.styleKey = basemap;
    this.map = new maplibregl.Map({
      container: el, style: STYLE[basemap], bounds: [[w, s], [e, n]],
      fitBoundsOptions: { padding: window.innerWidth > 900 ? { top: 20, bottom: 110, left: 400, right: 40 } : { top: 20, bottom: Math.round(window.innerHeight * 0.52), left: 10, right: 10 } },
      attributionControl: { compact: true }, maxZoom: 17,
      transformRequest: (url) => (KEY && url.includes("basemaps.cartocdn.com") ? { url: `${url}${url.includes("?") ? "&" : "?"}key=${KEY}` } : undefined),
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    this.map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    this.map.on("click", (ev) => onClick([ev.lngLat.lng, ev.lngLat.lat]));
    this.ready = new Promise((r) => this.map.once("load", () => r()));
    // setStyle() wipes our layers: put them back once the new basemap is in.
    this.map.on("style.load", () => this.restore());
  }

  setBasemap(kind: Basemap) {
    if (kind === this.styleKey) return;
    this.styleKey = kind;
    for (const s of this.slots.values()) s.current = null;
    this.map.setStyle(STYLE[kind], { diff: false });
  }

  /** Layer position: just under the first label, so place names stay readable over the data. */
  private before(): string | undefined {
    const layers = this.map.getStyle()?.layers ?? [];
    return layers.find((l) => l.id === "labels")?.id ?? layers.find((l) => l.type === "symbol")?.id;
  }

  private restore() {
    for (const [slot, s] of this.slots) if (s.spec) this.install(slot, s, s.spec, true);
    this.drawGauges();
  }

  private install(slot: string, s: Slot, spec: RasterSpec, visible: boolean): string {
    const id = `${slot}-${++s.n}`;
    this.map.addSource(id, { type: "raster", tiles: [spec.tiles], tileSize: 256, maxzoom: spec.maxzoom });
    this.map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": visible ? spec.opacity : 0, "raster-fade-duration": 0, "raster-resampling": "nearest" } }, this.before());
    s.current = id;
    this.reorder();
    return id;
  }

  /** Keep the stacking order fixed no matter which layer was switched on last. */
  private reorder() {
    const before = this.before();
    for (const slot of STACK) {
      const id = this.slots.get(slot)?.current;
      if (id && this.map.getLayer(id)) this.map.moveLayer(id, before);
    }
  }

  private drop(id: string) {
    if (this.map.getLayer(id)) this.map.removeLayer(id);
    if (this.map.getSource(id)) this.map.removeSource(id);
  }

  /** Show a tile layer, or null to hide it. A changed tile URL is loaded behind the old one and swapped in only once its tiles have arrived. */
  setRaster(slot: string, spec: RasterSpec | null) {
    let s = this.slots.get(slot);
    if (!s) this.slots.set(slot, (s = { n: 0, spec: null, current: null }));
    const prev = s.spec;
    s.spec = spec;
    if (!this.map.isStyleLoaded() && !this.map.getStyle()) return;
    if (!spec) { if (s.current) this.drop(s.current); s.current = null; return; }
    if (prev && prev.tiles === spec.tiles && s.current && this.map.getLayer(s.current)) {
      this.map.setPaintProperty(s.current, "raster-opacity", spec.opacity);
      return;
    }
    const old = s.current;
    if (!old || !this.map.getLayer(old)) { this.install(slot, s, spec, true); return; }
    const fresh = this.install(slot, s, spec, false);
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      this.map.off("sourcedata", check);
      if (s!.current !== fresh) { this.drop(fresh); return; } // superseded by a newer request
      if (this.map.getLayer(fresh)) this.map.setPaintProperty(fresh, "raster-opacity", spec.opacity);
      setTimeout(() => this.drop(old), 200);
    };
    const check = (e: maplibregl.MapSourceDataEvent) => { if (e.sourceId === fresh && this.map.isSourceLoaded(fresh)) finish(); };
    this.map.on("sourcedata", check);
    setTimeout(finish, 5000);
  }

  setGauges(fc: GeoJSON.FeatureCollection | null, onPick: (id: string, at: LonLat) => void) {
    this.gauges = fc;
    this.onGauge = onPick;
    if (this.map.getStyle()) this.drawGauges();
  }

  private drawGauges() {
    for (const id of ["gauges-label", "gauges"]) if (this.map.getLayer(id)) this.map.removeLayer(id);
    if (this.map.getSource("gauges")) this.map.removeSource("gauges");
    if (!this.gauges) return;
    this.map.addSource("gauges", { type: "geojson", data: this.gauges });
    this.map.addLayer({
      id: "gauges", type: "circle", source: "gauges",
      paint: { "circle-radius": 7, "circle-stroke-width": 2, "circle-stroke-color": "#ffffff", "circle-color": ["step", ["get", "ratio"], "#6B7280", 0, LEVEL_COLOR.normal, 1.5, LEVEL_COLOR.watch, 2, LEVEL_COLOR.warning, 3, LEVEL_COLOR.emergency] },
    });
    this.map.off("click", "gauges", this.gaugeClick);
    this.map.on("click", "gauges", this.gaugeClick);
  }

  private gaugeClick = (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (f) { e.originalEvent.stopPropagation(); this.onGauge?.(String(f.properties?.id), [e.lngLat.lng, e.lngLat.lat]); }
  };

  zones(z: ZoneRisk[], onPick: (z: ZoneRisk) => void) {
    this.zoneMarkers.forEach((m) => m.remove());
    this.zoneMarkers = [];
    const order = ["normal", "watch", "warning", "emergency"];
    for (const zr of z) {
      const el = document.createElement("button");
      el.className = `zone-pin ${zr.level}${order.indexOf(zr.level) > order.indexOf(zr.previous) ? " rising" : ""}`;
      el.setAttribute("aria-label", `${zr.place.name}: ${zr.level}`);
      el.innerHTML = `<span class="zone-name">${zr.place.name}</span>`;
      el.addEventListener("click", (e) => { e.stopPropagation(); onPick(zr); });
      this.zoneMarkers.push(new maplibregl.Marker({ element: el }).setLngLat(zr.place.at).addTo(this.map));
    }
  }

  clearZones() { this.zones([], () => undefined); }

  setPin(p: LonLat | null) {
    this.pin?.remove();
    this.pin = null;
    if (!p) return;
    const el = document.createElement("div");
    el.className = "pin";
    this.pin = new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat(p).addTo(this.map);
  }

  flyTo(p: LonLat, zoom = 13) {
    this.map.flyTo({ center: p, zoom, padding: window.innerWidth > 900 ? { left: 380, top: 0, right: 0, bottom: 60 } : { left: 0, top: 0, right: 0, bottom: 200 } });
  }
}
