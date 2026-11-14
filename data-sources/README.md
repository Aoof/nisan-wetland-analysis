# data-sources

There is one sandbox per source. All of them use the same area: Coatzacoalcos, Veracruz, bounding box `(-94.90, 17.60, -94.00, 18.30)`.

All rasters use the same UTM 15N grid, so layers from different sandboxes can be stacked without reprojecting. Most are at 30 m; SWOT is at 100 m and SMAP stays on its own 9 km grid.

Each sandbox has its own `.venv`, `requirements.txt` and README. Downloads and outputs go to `data/`, which is git-ignored.

| Sandbox | Source | Login | Status |
|---|---|---|---|
| `copernicus-dem-sandbox` | GLO-30 elevation + HAND (AWS) | none | Run end to end |
| `smap-sandbox` | SMAP L3/L4 soil moisture (NSIDC) | Earthdata | Live search checked; the processing tested on synthetic files |
| `sentintel-sandbox` | OPERA DSWx-S1 / DSWx-HLS / RTC-S1 (PO.DAAC, ASF) | Earthdata | Live search checked; the processing tested on synthetic files |
| `nisar-sandbox` | NISAR L2 GCOV (ASF) | Earthdata | Live search checked; the processing tested on synthetic files |
| `swot-sandbox` | SWOT HR Raster 100 m (PO.DAAC) | Earthdata | Live search checked; the processing tested on synthetic files |
| `radarsat-sandbox` | RCM / RADARSAT-1 (Canada EODMS) | EODMS | Untested: EODMS needs an account even to search |

**Order:** run `copernicus-dem-sandbox` first. NISAR uses its sea mask, and HAND is the "where does water go next" layer.
