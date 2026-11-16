# API reference

All routes are `GET`, under `/api`, on the same origin as the app. JSON responses carry an `ETag` (send `If-None-Match` to get a 304) and `Cache-Control` with `stale-while-revalidate`. CORS allows any origin for `GET`.

The API answers from its local cache only. A source that has not been fetched yet returns an empty or pending result, not an error.

## Status

| Route | Returns |
|---|---|
| `/api/health` | `{ ok, time, bbox, earthdata }`. `earthdata` is `true` when a token is configured. Used by the container health check. |
| `/api/now` | Everything the first screen needs: latest pass per water product (`water[prod]` with `id`, `t`, `tiles`, `count`, area statistics), the HAND tile template, the latest NISAR image, `forecastUpdated`, and `sources` (status per source: `state`, `message`, `newest`, `updated_at`). |

## Forecast and places

| Route | Returns |
|---|---|
| `/api/forecast` | GloFAS and weather for the gauges and places in `places.json`. `gauges[]`: `days`, `q`, `qMax` (m³/s, 92 days back and 30 ahead), `clim50`, `clim90` (2006–2025 day-of-year median and 90th percentile). `places[]`: hourly `rain` (mm), `wetness` (0–1 of saturation) and daily values. `503` until the first fetch completes. |
| `/api/places` | Per zone: `shares` (fraction of the zone in each HAND class `"1"`–`"4"`) and `water[prod]` (water share per pass). Drives the zone risk. |
| `/api/point?lon=&lat=` | `terrain` (`cls` 1–4 or 0 for sea / no data, `hand_m`, `elevation_m`) and `water[prod]`: the class at that point for every pass (`0` dry, `1` open water, `2` partial, `3` water under vegetation, `255` not observed). `422` outside the basin. |

## Satellite passes and series

| Route | Returns |
|---|---|
| `/api/timeline/{source}` | Acquisitions for `opera-dswx-s1`, `opera-dswx-hls`, `nisar-gcov`, `smap-l4` or `swot-raster`: `id`, `t`, `tiles`, `processed`. |
| `/api/passes/{prod}` | Processed OPERA passes with basin statistics: `t`, `observed_fraction`, `water_km2`, `open_km2`, `partial_km2`, `veg_km2`. |
| `/api/series/{source}` | Column-oriented series for `smap-l4` (`rootzone_wetness`, `surface_wetness`, `rootzone_m3m3`, `surface_m3m3`) or `swot-raster` (`wse_median_m`, `wse_p10_m`, `wse_p90_m`, `water_area_km2`). While the first fill runs: `{ t: [], pending: true, status }`. |

## Tiles

Web Mercator XYZ PNG, 256 px, nearest-neighbour. Transparent where there is no data.

| Route | Content |
|---|---|
| `/api/tiles/opera-dswx-s1/{pass}/{z}/{x}/{y}.png` | Radar water: blue open water, teal water under vegetation |
| `/api/tiles/opera-dswx-hls/{pass}/{z}/{x}/{y}.png` | Optical water: blue open water, light blue partial |
| `/api/tiles/hand/{z}/{x}/{y}.png?v=` | HAND classes 1 (red) and 2 (orange); immutable per `v` |
| `/api/tiles/nisar-gcov/{granule}/{z}/{x}/{y}.png` | NISAR HH/HV backscatter composite |

`pass` and `granule` IDs come from `/api/now` or `/api/timeline/{source}`.

FastAPI's interactive docs are at `/docs` while the API runs.
