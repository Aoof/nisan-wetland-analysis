/** What each source is, and what the API delivers for it. Shown to researchers in Settings. */
import type { SourceContract, SourceId, SourceMeta } from "./types";

const meta = (m: SourceMeta) => m;

export const CATALOG: Record<SourceId, { meta: SourceMeta; contract: SourceContract }> = {
  "dem-hand": {
    meta: meta({
      id: "dem-hand", name: "Flood-prone ground (HAND)", sensor: "Copernicus GLO-30 DEM (TanDEM-X) + ASF/NASA GLO-30 HAND",
      answers: "Where does water go first when rivers rise?", measures: ["elevation (m, EGM2008)", "height above nearest drainage (m)"],
      resolution: "30 m", revisit: "static (2011–2015 data)", latency: "n/a", auth: "none",
      caveats: ["Surface heights: roofs and canopy, not the ground, in towns and forest.", "Class breaks of 1, 5 and 15 m are generic and not yet checked against past floods.", "The sea mask is approximate; coastal lagoons at 0 m are masked too."],
      citation: "Copernicus DEM GLO-30 © DLR/Airbus, ESA; GLO-30 HAND, ASF/NASA (2021).", color: "#D9622B",
    }),
    contract: {
      endpoint: [
        { path: "GET /api/tiles/hand/{z}/{x}/{y}.png", format: "PNG tiles, Web Mercator", fields: { "red": "HAND class 1 (0–1 m above drainage)", "orange": "HAND class 2 (1–5 m)" } },
        { path: "GET /api/point → terrain", format: "JSON", fields: { cls: "1–4 (0 = sea / no data)", hand_m: "m above nearest drainage", elevation_m: "m above EGM2008" } },
      ],
      upstream: [
        { path: "public COGs on AWS Open Data: copernicus-dem-30m, glo-30-hand (1×1° tiles)", format: "GeoTIFF float32, range-read for the basin only", fields: { band1: "metres" }, note: "Fetched once by the API; cached in data/dem." },
        { path: "API cache: data/dem/coatzacoalcos_hand_class_utm15n.tif", format: "GeoTIFF uint8, EPSG:32615, 30 m", fields: { band1: "1: 0–1 m, 2: 1–5 m, 3: 5–15 m, 4: >15 m, 0: sea / no data" } },
      ],
    },
  },
  "opera-dswx-s1": {
    meta: meta({
      id: "opera-dswx-s1", name: "Surface water (radar)", sensor: "Sentinel-1 C-band SAR → NASA OPERA DSWx-S1",
      answers: "Where is there water right now, even under cloud?", measures: ["open water", "inundated vegetation"],
      resolution: "30 m (browse images ≈107 m)", revisit: "about 6–12 days", latency: "about 1–2 days", auth: "earthdata",
      caveats: ["Wind-roughened water can look dry.", "Steep slopes are masked by OPERA's own HAND filter.", "Check the observed share before comparing dates."],
      citation: "OPERA Project, OPERA_L3_DSWX-S1_V1, NASA PO.DAAC.", color: "#2F6DB5",
    }),
    contract: {
      endpoint: [
        { path: "GET /api/tiles/opera-dswx-s1/{pass}/{z}/{x}/{y}.png", format: "PNG tiles", fields: { blue: "open water (1)", teal: "inundated vegetation (3)", transparent: "dry (0) or not observed (255)" } },
        { path: "GET /api/passes/opera-dswx-s1", format: "JSON", fields: { t: "ISO time", observed_fraction: "0–1 of inland area", water_km2: "all water", open_km2: "", veg_km2: "" } },
        { path: "GET /api/point → water", format: "JSON", fields: { "[].t": "pass time", "[].code": "0 dry, 1 open, 2 partial, 3 vegetated water, 255 not observed" } },
      ],
      upstream: [
        { path: "public BROWSE.png per MGRS tile (PODAAC)", format: "paletted PNG 1024×1024 over a 109.8 km tile", fields: { "palette index": "WTR class", anchoring: "NW corner of the 100 km MGRS square" } },
        { path: "API cache: data/passes/opera-dswx-s1/*.tif", format: "GeoTIFF uint8, Web Mercator 100 m, one per pass", fields: { WTR: "0 dry, 1 open, 2 partial, 3 vegetated, 255 not observed" } },
      ],
    },
  },
  "opera-dswx-hls": {
    meta: meta({
      id: "opera-dswx-hls", name: "Surface water (optical)", sensor: "Landsat 8/9 + Sentinel-2 → NASA OPERA DSWx-HLS",
      answers: "Where is there water, including partly flooded ground, on clear days?", measures: ["open water", "partial surface water"],
      resolution: "30 m (browse images ≈107 m)", revisit: "about 2–3 days, cloud permitting", latency: "about 1–2 days", auth: "earthdata",
      caveats: ["Clouds block it: in the rainy season many dates are mostly unobserved.", "Partial water is a mixed pixel, not a depth."],
      citation: "OPERA Project, OPERA_L3_DSWX-HLS_V1, NASA PO.DAAC.", color: "#6FA8DC",
    }),
    contract: {
      endpoint: [{ path: "GET /api/tiles/opera-dswx-hls/{pass}/{z}/{x}/{y}.png", format: "PNG tiles", fields: { blue: "open water", "light blue": "partial surface water" } }],
      upstream: [
        { path: "public BROWSE.png per MGRS tile (PODAAC)", format: "paletted PNG 1024×1024 over a 109.8 km tile", fields: { "palette index": "WTR class" } },
        { path: "API cache: data/passes/opera-dswx-hls/*.tif", format: "GeoTIFF uint8, Web Mercator 100 m, one per pass", fields: { WTR: "0 dry, 1 open, 2 partial, 255 not observed" } },
      ],
    },
  },
  "nisar-gcov": {
    meta: meta({
      id: "nisar-gcov", name: "Wetland radar (NISAR)", sensor: "NASA-ISRO NISAR L-band SAR, L2 GCOV (ASF DAAC)",
      answers: "Where is water hiding under mangroves and swamp forest?", measures: ["HH / HV backscatter (dB)", "open water", "flooded vegetation"],
      resolution: "30 m", revisit: "12 days", latency: "about 2 days", auth: "earthdata",
      caveats: ["Water-class thresholds are untuned L-band starting points.", "Provisional products may be reprocessed.", "The image shown is a backscatter composite, not a water map."],
      citation: "NASA/ISRO NISAR L2 GCOV, ASF DAAC.", color: "#4B6584",
    }),
    contract: {
      endpoint: [{ path: "GET /api/tiles/nisar-gcov/{granule}/{z}/{x}/{y}.png", format: "PNG tiles", fields: { RGB: "HH/HV backscatter composite" } }],
      upstream: [
        { path: "public *_LATLON.png + .kml (gx:LatLonQuad)", format: "PNG on a lat/lon grid", fields: { corners: "lower-left, lower-right, upper-right, upper-left" } },
        { path: "API cache: data/nisar/<granule>.tif", format: "GeoTIFF RGBA, EPSG:4326, latest passes covering the basin", fields: { RGB: "backscatter composite" } },
      ],
    },
  },
  "swot-raster": {
    meta: meta({
      id: "swot-raster", name: "Water level (SWOT)", sensor: "NASA/CNES SWOT KaRIn, L2 HR Raster 100 m (PO.DAAC)",
      answers: "How high is the water in the river and lagoons, and is it rising?", measures: ["water surface elevation (m, EGM2008)", "water area"],
      resolution: "100 m", revisit: "about 21 days", latency: "about 2–5 days", auth: "earthdata",
      caveats: ["Cannot see water under dense vegetation.", "The basin-wide median mixes river, lagoons and sea."],
      citation: "SWOT Level 2 KaRIn High Rate Raster, NASA/CNES, PO.DAAC.", color: "#1B9AAA",
    }),
    contract: {
      endpoint: [{ path: "GET /api/series/swot-raster", format: "JSON columns", fields: { t: "pass time", wse_median_m: "m EGM2008", wse_p10_m: "m", wse_p90_m: "m", water_area_km2: "km²" } }],
      upstream: [
        { path: "SWOT_L2_HR_Raster_100m_D NetCDF tiles in UTM 15 (PO.DAAC, Earthdata token)", format: "NetCDF4, read over HTTPS for the basin only", fields: { wse: "m", wse_qual: "0 good … 3 bad", water_frac: "0–1", water_area: "m²" } },
        { path: "API cache: data/cache/swot-raster/<tile>.npz", format: "basin cut on the UTM 15N 100 m grid, one per tile", fields: { wse_median_m: "per pass, quality ≤ suspect and water ≥ 50 %", good_water_pixels: "count" } },
      ],
    },
  },
  "smap-l4": {
    meta: meta({
      id: "smap-l4", name: "Soil saturation (SMAP)", sensor: "NASA SMAP L-band radiometer; L4 assimilation (GMAO), NSIDC DAAC",
      answers: "How soaked is the ground, so how fast will new rain turn into flooding?", measures: ["root-zone wetness (0 wilting – 1 saturated)", "surface soil moisture (m³/m³)"],
      resolution: "9 km", revisit: "3-hourly (one per day kept)", latency: "about 2–3 days", auth: "earthdata",
      caveats: ["9 km cells: a regional signal, not a field or a street.", "Wetland and coastal cells are often quality-flagged."],
      citation: "Reichle et al., SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture, v8, NSIDC DAAC.", color: "#8A6D3B",
    }),
    contract: {
      endpoint: [{ path: "GET /api/series/smap-l4", format: "JSON columns", fields: { t: "ISO time", rootzone_wetness: "0–1", surface_wetness: "0–1", rootzone_m3m3: "", surface_m3m3: "" } }],
      upstream: [
        { path: "SPL4SMGP v008 HDF5 granules, 13:30 UTC daily (NSIDC, Earthdata token)", format: "HDF5, EASE-Grid 2.0 9 km; only the basin rows and columns are read", fields: { sm_rootzone_wetness: "0–1", sm_surface: "m³/m³" } },
        { path: "API cache: data/cache/smap-l4/<granule>.npz", format: "basin window per granule", fields: { "series value": "mean over land cells" } },
      ],
    },
  },
  radarsat: {
    meta: meta({
      id: "radarsat", name: "Historical radar (RADARSAT)", sensor: "RADARSAT-1 and RADARSAT Constellation Mission, C-band SAR (EODMS, Canada)",
      answers: "How did floods look here in the past 30 years?", measures: ["C-band backscatter (raw)"], resolution: "about 30 m", revisit: "irregular", latency: "orders take hours", auth: "eodms",
      caveats: ["Needs an EODMS account.", "Raw SAR: needs terrain correction and classification first.", "RCM rarely images Mexico."],
      citation: "RADARSAT-1 / RCM data © Government of Canada, EODMS.", color: "#A33B3B",
    }),
    contract: { endpoint: [], upstream: [{ path: "EODMS catalogue (not wired yet)", format: "needs an EODMS account", fields: {} }] },
  },
  forecast: {
    meta: meta({
      id: "forecast", name: "River and rain forecast", sensor: "GloFAS v4 river discharge (Copernicus EMS); ECMWF rain and soil moisture, via Open-Meteo",
      answers: "Will the rivers rise and how much rain is coming in the next days?", measures: ["river discharge (m³/s)", "precipitation (mm)", "soil moisture (m³/m³)"],
      resolution: "GloFAS about 5 km; weather about 9–25 km", revisit: "daily (rivers), hourly (weather)", latency: "hours", auth: "none",
      caveats: ["GloFAS is a model at about 5 km: it covers the main rivers, not urban drains or small creeks.", "Model soil moisture stands in for SMAP until SMAP values arrive.", "Saturation assumes porosity 0.47 everywhere."],
      citation: "Open-Meteo.com (CC BY 4.0); GloFAS, Copernicus Emergency Management Service; ECMWF.", color: "#7B5EA7",
    }),
    contract: {
      endpoint: [{ path: "GET /api/forecast", format: "JSON", fields: { "gauges[].q / qMax": "m³/s, 92 days back + 30 ahead", "gauges[].clim50 / clim90": "2006–2025 day-of-year median / 90th percentile", "places[].rain": "mm per hour", "places[].wetness": "0–1 share of saturation" } }],
      upstream: [
        { path: "https://flood-api.open-meteo.com/v1/flood", format: "JSON", fields: { river_discharge: "m³/s" } },
        { path: "https://api.open-meteo.com/v1/forecast", format: "JSON", fields: { precipitation: "mm/h", "soil_moisture_*": "m³/m³" } },
      ],
    },
  },
};

export const SOURCE_ORDER: SourceId[] = ["forecast", "opera-dswx-s1", "dem-hand", "opera-dswx-hls", "nisar-gcov", "swot-raster", "smap-l4", "radarsat"];
