# Architecture

NISAN has two parts that ship as one container:

| Part | Stack | Job |
|---|---|---|
| `nisan-api/` | Python 3.12, FastAPI, rasterio, rio-tiler, APScheduler | Owns every upstream request and every credential. Downloads only the basin's part of each product, puts it on a shared grid, caches it on disk and serves tiles and JSON. |
| `nisan-app/` | TypeScript, Vite, MapLibre GL, TanStack Query core, IndexedDB | The map, the two views (Overview, Authorities), the Settings sheet and the risk rules. |

The browser only talks to `/api` on its own origin. It never calls NASA, Copernicus or Open-Meteo itself, and it never sees our Earthdata token.

```
 upstreams                         nisan-api                              nisan-app (browser)
 ─────────                         ─────────                              ───────────────────
 NASA CMR + PO.DAAC browse  ─┐
 ASF NISAR browse           ─┤    background jobs (APScheduler)
 AWS Open Data DEM / HAND   ─┼──▶ ─ fetch basin cut only ─▶ /data cache ─▶ /api/now, /api/forecast ──▶ stale-while-revalidate
 NSIDC SMAP, PO.DAAC SWOT   ─┤    (Earthdata token, server only)          /api/tiles/... (XYZ PNG)     cache (IndexedDB)
 Open-Meteo GloFAS + ECMWF  ─┘                                            /api/point, /api/places      │
                                                                          /api/series, /api/timeline   ▼
                                                                                               risk rules (src/fusion)
                                                                                                         │
                                                                                                         ▼
                                                                                               map + panels + time bar
```

## API: answer from disk, refresh in the background

Endpoints never wait on an upstream. Every request is answered from the last good copy in `NISAN_DATA` (default `nisan-api/data/`), and jobs refresh that copy on a schedule (`app/jobs.py`):

| Job | Every | Source |
|---|---|---|
| River and rain forecast | 1 h | Open-Meteo (GloFAS v4, ECMWF) |
| Radar water (DSWx-S1) | 3 h | OPERA via CMR + PO.DAAC browse images |
| Optical water (DSWx-HLS) | 3 h | OPERA via CMR + PO.DAAC browse images |
| NISAR image | 6 h | ASF browse PNG + KML |
| SMAP soil moisture | 12 h | NSIDC, Earthdata token |
| SWOT water level | 24 h | PO.DAAC, Earthdata token |
| Terrain (DEM + HAND) | once | AWS Open Data; delete `data/dem/` to rebuild |

On start-up the jobs run in the order the first screen needs them: forecast and terrain, then the latest radar water map, then optical and NISAR, then SMAP and SWOT. A failed job only changes that source's status message (`live`, `refreshing`, `awaiting-data`, `unavailable`, `error`). The app shows these statuses under Settings → Data.

The scheduler runs inside the API process, so **run exactly one worker and one replica**. More workers would run every job more than once.

### One grid for every raster

We put every raster on a shared grid before serving it (`app/geo.py`): Web Mercator at 100 m for water maps, UTM 15N at 30 m for terrain. rio-tiler then cuts XYZ PNG tiles with nearest-neighbour resampling, so water classes are never blended. The browser never places an image by its corners. `tests/test_alignment.py` checks the georeferencing: open water in a DSWx pass has to sit in DEM valleys (mean HAND close to 0 m).

### Caching over HTTP

JSON responses carry an `ETag` and `Cache-Control: max-age, stale-while-revalidate`, so revalidation costs a 304. The HAND tile URL carries a `?v=` version so those tiles can be cached for good.

## App: draw first, then fetch

`src/data/store.ts` loads data fastest-first:

1. The last session's data is restored from IndexedDB (TanStack Query persister, kept for 7 days) and drawn at once.
2. `/api/now` and `/api/forecast` (small, high priority) bring the latest water map and the forecast.
3. When the browser is idle it loads the rest: per-place statistics, timelines, water-area history, SMAP and SWOT series.
4. Everything refreshes every 10 minutes, and when the tab comes back after more than 5 minutes away.

Consumers subscribe to topics (`now`, `forecast`, `places`, `timeline`, `passes`, `series`, `status`). `main.ts` maps each topic to the parts of the screen it affects and repaints at most once per animation frame.

The risk rules run in the browser (`src/fusion/`). Moving the time bar re-evaluates every zone without a request to the API. They are described in [risk-model.md](risk-model.md).

## Code map

```
nisan-api/app/
  main.py         routes; mounts the built app at / in the container
  jobs.py         refresh schedule and start-up order
  settings.py     paths, basin bounding box, credentials (read from nisan-app/.env)
  geo.py          shared grids, MGRS tile origins
  tiles.py        XYZ PNG tiles via rio-tiler
  store.py        atomic JSON files and the source status registry
  cmr.py          NASA CMR granule search
  web.py          static files for the built app
  sources/        one module per upstream: opera, nisar, dem, forecast, earthdata (+ smap, swot)
nisan-api/tests/  offline tests; the alignment test needs a built pass and terrain

nisan-app/src/
  main.ts         state, render scheduling, search, view switching
  data/           API client, stale-while-revalidate cache, store, settings, places.json
  fusion/         forecast helpers and the risk rules
  adapters/       shared types and the source catalogue shown under Research tools
  ui/             map, time bar, charts, panels, intro dialog
```

`nisan-app/src/data/places.json` lists the 11 zones and 5 river gauges. The API reads the same file, so both sides always agree on the zones.
