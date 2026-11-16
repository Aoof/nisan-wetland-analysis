# NISAN: flood and wetland watch for the lower Coatzacoalcos basin

NISAN maps how the wetlands and floodplains of the lower Coatzacoalcos basin in Veracruz, Mexico, grow and shrink over time, and uses that history to show where water is likely to go next.

## Why NISAN

Several satellites watch this basin, and each one sees a different part of the water cycle. Radar from Sentinel-1 picks up open water through cloud. NASA and ISRO's new NISAR satellite uses a longer radar wavelength that reaches water hidden under mangroves and swamp forest. SMAP measures how wet the soil is, SWOT measures how high rivers and lagoons stand, and river and rain forecasts add what is still to come. A digital elevation model tells us how far each spot sits above the nearest stream. On their own, these datasets live in different archives, in different formats, and mostly in the hands of specialists. NISAN brings them together on one map that anyone can read.

The same information serves very different people. Someone living near the river may need to know whether to act now. A farmer may want an educated guess about when the ground is dry enough to plant, or how wet the coming week will be. A local authority may want to see which districts are rising and share a short brief. A researcher may want the readings themselves. NISAN starts every answer with a plain risk level (normal, watch, warning or emergency), the reasons behind it and what to do, and keeps the deeper layers, charts and downloads one step away for anyone who wants them.

We want people to be able to see, understand and communicate the data, so the rules that turn readings into a risk level are deliberately simple. Each instrument contributes a signal that is easy to picture: the river is twice its usual flow, a certain amount of rain is forecast, the radar sees more water than usual, the ground is already saturated. Every verdict lists the signals that produced it, and the thresholds are published inside the app. Places that are wet most of the year are shown as wetland, lagoon or river rather than as floods, so they don't raise false alarms. Every reading shows its age, because some satellites only pass every few days or weeks and people acting on the data need to know how current it is.

We built NISAN in two days for the NASA Space Apps Challenge, so this version covers one test area. We chose the lower Coatzacoalcos basin because our team has personal ties to it, it floods often, and cities, farmland and wetlands sit side by side within a small area. Next we want to add more basins, get more out of the data each satellite collects, and study better ways to present it.

NISAN isn't an official warning service. In an emergency, follow your local civil protection instructions. The thresholds are provisional and have not been reviewed by a local authority.

## Using the app

The Overview answers one question for any spot in the basin: is water coming here? You can search a street, a town or a `lat, lon` pair, or tap the map. The answer card shows the level, the reasons, what to do, and the water history at that spot as seen by radar.

The Authorities view ranks the 11 named zones, marks the ones that rose in the last 24 hours, shows each river gauge's forecast peak for the next 10 days, and puts a data-age clock next to every source. From there you can copy a plain-text brief or download a CSV of all zones.

A time bar along the bottom runs from 120 days of past satellite passes to 30 days of forecast. Moving it recomputes every zone and answer for that moment. Settings holds the basemap, the extra layers (optical water and the NISAR radar image), soil and rain charts for farm use, and research tools with every source's description, caveats, thresholds and exports.

## How it works

The project has two parts that ship as one Docker image. The data API in [`nisan-api/`](nisan-api) is written in Python with FastAPI. Background jobs in [`jobs.py`](nisan-api/app/jobs.py) fetch every source on a schedule, read only the part of each file that covers the basin, put every raster on a shared grid ([`geo.py`](nisan-api/app/geo.py)) and cache the results on disk. Each upstream has its own module in [`app/sources/`](nisan-api/app/sources). The API answers every request from that cache, so a slow satellite archive never holds up the map, and the NASA Earthdata token stays on the server.

The web app in [`nisan-app/`](nisan-app) is TypeScript with MapLibre GL. It opens on the last saved copy of the data from the browser's IndexedDB, then refreshes in the background ([`store.ts`](nisan-app/src/data/store.ts)). The risk rules live in [`risk.ts`](nisan-app/src/fusion/risk.ts) and [`forecast.ts`](nisan-app/src/fusion/forecast.ts) and run in the browser. The 11 zones and 5 river gauges are defined once in [`places.json`](nisan-app/src/data/places.json), which both halves read.

The full design is in [docs/architecture.md](docs/architecture.md), and every rule and threshold is in [docs/risk-model.md](docs/risk-model.md).

## Quick start

One container serves the app at `/` and the API at `/api`. Put `CARTO_API_KEY` and `EARTHDATA_TOKEN` in `nisan-app/.env`, then run:

```bash
docker compose --env-file nisan-app/.env up -d --build
```

Open `http://localhost:8000`. On first start the API downloads the terrain and the latest maps in the background, and the app fills in as data arrives. `EARTHDATA_TOKEN` is only needed for SMAP and SWOT. Run a single replica, because the refresh jobs run inside the process. [docs/deployment.md](docs/deployment.md) covers Compose, configuration and volumes, and [docs/development.md](docs/development.md) covers running the API and the app locally.

## Documentation

| Document | Covers |
|---|---|
| [Architecture](docs/architecture.md) | Components, data flow, refresh schedule, caching, code map |
| [Risk model](docs/risk-model.md) | How levels are computed, every threshold, known limits |
| [Data sources](docs/data-sources.md) | Each dataset, how we fetch it, credits |
| [API reference](docs/api.md) | Every `/api` route |
| [Deployment](docs/deployment.md) | Docker, configuration, operating notes |
| [Development](docs/development.md) | Running locally, tests, common changes |
| [Design](docs/design.md) | Visual and interaction rules |
| [Roadmap](docs/roadmap.md) | Open questions and next steps |

## Team

NISAN was built by Andres Lara-Trevino, Abdulrahman Mousa and Edicson Garcia.

## Credits

Data from NASA (OPERA, NISAR with ISRO, SMAP, SWOT with CNES), Copernicus (GLO-30 DEM, GloFAS), ECMWF via Open-Meteo, and ASF. Basemaps © CARTO and OpenStreetMap contributors; imagery © Esri. Full citations are in [docs/data-sources.md](docs/data-sources.md).
