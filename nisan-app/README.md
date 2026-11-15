# nisan-app

Map-first flood watch for the lower Coatzacoalcos basin. Two views:

- **Overview** (default): search or tap the map for a plain answer about that spot: risk level, why, what to do, and the water history seen by satellite.
- **Authorities**: a status band in the current risk colour, zones ranked with what rose in 24 hours, the river hydrograph, signals, data-freshness clocks, a copyable brief and a zones CSV.

**Settings** (gear icon) holds everything else, most important first: basemap, surface water, flood-prone ground, farm details (soil and rain charts), more layers (optical water, NISAR radar image) and research tools (sources, methods, thresholds, exports). Choices are remembered in this browser.

Design rules are in [DESIGN.md](DESIGN.md); the plan is in [PLAN.md](PLAN.md).

## Run

Two processes: the data API and the app.

```bash
# 1. secrets, in nisan-app/.env (git-ignored)
#    CARTO_API_KEY=...        map tiles (public by design; restrict it to your domains in CARTO)
#    EARTHDATA_TOKEN=...      NASA Earthdata token; used only by the API, never sent to the browser

# 2. API (first start fetches data in the background; the app shows what is ready)
cd ../nisan-api && uv sync && uv run python -m app

# 3. app
npm install && npm run dev        # http://localhost:5173
```

Run the API tests with `cd ../nisan-api && uv run pytest`. They include a check that rivers in the water maps sit in DEM valleys, which is how the map alignment is verified.

## How data gets to the screen

1. The app restores the last session's data from IndexedDB and draws it immediately.
2. `/api/now` and `/api/forecast` (small, high priority) bring the latest water map and the forecast, and the screen updates.
3. When the browser is idle it loads the rest: place statistics, timelines, water-area history, SMAP and SWOT series.
4. Everything refreshes in the background every 10 minutes and when the tab regains focus. Failures show a note in Settings and never block the rest.
5. Rasters are Web Mercator XYZ tiles cut by the API (rio-tiler); the browser never places images by interpolating corners.

## Code map

- `src/data/`: typed API client, stale-while-revalidate cache (TanStack Query core + IndexedDB), the store and its boot order, settings.
- `src/fusion/`: forecast helpers and the risk rules (zones, point answers, brief). Thresholds are provisional and shown under Research tools.
- `src/adapters/`: shared types and the source catalogue (what each source is and what the API and sandboxes deliver).
- `src/ui/`: map, time bar, charts, panels.
