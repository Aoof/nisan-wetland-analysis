# Development

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm

## Secrets

Both halves read `nisan-app/.env` (git-ignored):

```dotenv
CARTO_API_KEY=...      # map tiles; public by design, restrict it to your domains in CARTO
EARTHDATA_TOKEN=...    # NASA Earthdata token; read only by the API, never sent to the browser
```

Vite only exposes variables prefixed `VITE_` or `CARTO_` to the browser (`vite.config.ts`), so `EARTHDATA_TOKEN` can't leak into the bundle.

## Run

Two processes. The API first:

```bash
cd nisan-api && uv sync && uv run python -m app
```

It listens on `http://127.0.0.1:8000` and starts fetching data in the background. Then the app:

```bash
cd nisan-app && npm install && npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the API.

`npm run build` type-checks and builds to `nisan-app/dist/`; `npm run preview` serves that build with the same proxy.

## Tests

```bash
cd nisan-api && uv run pytest
```

The tests run offline. `test_alignment.py` checks that rivers in the water maps sit in DEM valleys, which is how the map georeferencing is verified; it skips unless a pass and the terrain are in `nisan-api/data/`.

```bash
cd nisan-app && npm run typecheck
```

## Common changes

- To add or move a zone or gauge, edit `nisan-app/src/data/places.json`. The API reads the same file, so restart it to recompute zone statistics.
- Thresholds live in `THRESHOLDS` in `nisan-app/src/fusion/forecast.ts`, and `HAND` in `risk.ts`. Update [risk-model.md](risk-model.md) in the same change; the Research tools table in the app reads the constants directly.
- To add a source, add a module in `nisan-api/app/sources/`, schedule it in `jobs.py`, expose it in `main.py`, describe it in `nisan-app/src/adapters/catalog.ts` and list it in [data-sources.md](data-sources.md).
- To see the "About NISAN" dialog again, run `localStorage.removeItem("nisan-intro-v1")` in the console, or open it from Settings → About and untick "Don't show this again".

Design rules for any UI change are in [design.md](design.md).

## Browser storage

| Key | Where | Holds |
|---|---|---|
| `nisan-settings-v1` | localStorage | View, basemap and layer toggles |
| `nisan-intro-v1` | localStorage | `"dismissed"` once "Don't show this again" is ticked |
| `nisan-query-cache-v1` | IndexedDB | Last API responses, kept 7 days, so the next visit draws at once |

`window.nisan` exposes `state`, `data`, `view`, `select`, `update` and `setView` for debugging in the console.
