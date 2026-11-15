# nisan-app plan

The current design is described in [README.md](README.md) (how it runs and how data reaches the screen) and [DESIGN.md](DESIGN.md) (visual rules). Summary of the architecture:

- **nisan-api** (`../nisan-api`, FastAPI): owns every upstream. It fetches CMR, OPERA browse images, NISAR browse images, Open-Meteo (GloFAS + ECMWF), and runs the SMAP and SWOT sandbox scripts with the server-side Earthdata token. It warps every raster onto one Web Mercator grid and serves XYZ tiles, per-point history, per-place statistics and JSON series, with ETag and Cache-Control headers. Background jobs refresh it; endpoints never wait on an upstream.
- **nisan-app** (this folder): MapLibre + a CARTO vector basemap, a stale-while-revalidate data layer (TanStack Query core + IndexedDB), and two views (Overview, Authorities) with a Settings sheet for the extras.

## Open questions

- Which zones do authorities think in: municipalities, colonias or watershed units?
- Risk thresholds are provisional and need sign-off before Authorities is shown to an authority.
- Do we host processed rasters ourselves long term, or serve COGs through a tiler such as TiTiler?
- SWOT per-reach series (RiverSP / LakeSP) and NISAR water classes need the sandboxes' output exported.
- Spanish: the app is English only for now.
