# Data sources

Our API fetches everything below, cuts it to the basin (W −94.90, S 17.60, E −94.00, N 18.30) and caches it in `NISAN_DATA`. The cache stays around 150 MB. The same descriptions are shown in the app under Settings → Research tools (from [`catalog.ts`](../nisan-app/src/adapters/catalog.ts)).

| Source | What it answers | Resolution | Revisit | Login | Used for |
|---|---|---|---|---|---|
| **River and rain forecast**: GloFAS v4 + ECMWF via Open-Meteo | Will rivers rise, how much rain is coming? | GloFAS ~5 km, weather 9–25 km | daily / hourly | none | River and rain drivers, model soil moisture |
| **Surface water (radar)**: OPERA DSWx-S1 (Sentinel-1) | Where is there water now, even under cloud? | 30 m (browse ≈107 m) | 6–12 days | none (public browse) | Main water layer, point history, zone water driver, basin signal |
| **Flood-prone ground**: Copernicus GLO-30 DEM + GLO-30 HAND | Where does water go first? | 30 m | static | none | Exposure classes, zone low-ground share |
| **Surface water (optical)**: OPERA DSWx-HLS (Landsat 8/9, Sentinel-2) | Where is water on clear days, including partial flooding? | 30 m (browse ≈107 m) | 2–3 days, cloud permitting | none (public browse) | Optional layer |
| **Wetland radar**: NISAR L2 GCOV (L-band) | Where is water under mangroves and swamp forest? | 30 m | 12 days | none (public browse) | Optional backscatter layer |
| **Water level**: SWOT L2 HR Raster 100 m | How high is the water, is it rising? | 100 m | ~21 days | `EARTHDATA_TOKEN` | Research series |
| **Soil saturation**: SMAP L4 (SPL4SMGP v008) | How soaked is the ground? | 9 km | one granule a day kept | `EARTHDATA_TOKEN` | Rain-threshold adjustment, farm charts |
| Historical radar: RADARSAT-1 / RCM | Past floods | ~30 m | irregular | EODMS account | Listed, not wired |

## How we fetch each source

- OPERA DSWx (S1 and HLS): CMR lists the granules; the public `BROWSE.png` per MGRS tile is a paletted PNG whose palette index is the water class. It is georeferenced from the tile ID (north-west corner of the 100 km MGRS square), warped to the shared Web Mercator grid and saved as one GeoTIFF per pass. `build_pass` in `opera.py` is where we would swap in full 30 m granules.
- NISAR: the public `*_LATLON.png` and its KML (`gx:LatLonQuad`) are written as an EPSG:4326 GeoTIFF; rio-tiler warps it per tile.
- DEM and HAND: public cloud-optimised GeoTIFFs on AWS Open Data; GDAL range-reads only the basin's part of each 1×1° tile. Downloaded once, about a minute.
- SMAP: each ~140 MB global HDF5 granule is read over HTTPS for the basin's EASE-Grid rows and columns only (about 11 s each). The 13:30 UTC granule is kept for each of the last 45 days.
- SWOT: NetCDF raster tiles are read over HTTPS, cut to the basin and snapped to a UTM 15N 100 m grid; adjacent scenes of a pass are merged. Last 120 days. Values with quality worse than "suspect" or under 50 % water are dropped.
- Forecast: one Open-Meteo flood call (92 days back, 30 ahead) for the 5 gauges and one weather call (31 days back, 10 ahead) for the 11 places. The 20-year GloFAS day-of-year median and 90th percentile are computed once on our server and cached.

Later refreshes only fetch what is new. A failed granule is retried on the next refresh.

## Credits

- OPERA Project, OPERA_L3_DSWX-S1_V1 and OPERA_L3_DSWX-HLS_V1, NASA PO.DAAC.
- NASA/ISRO NISAR L2 GCOV, ASF DAAC.
- Copernicus DEM GLO-30 © DLR/Airbus, ESA; GLO-30 HAND, ASF/NASA (2021).
- SWOT Level 2 KaRIn High Rate Raster, NASA/CNES, PO.DAAC.
- Reichle et al., SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture, v8, NSIDC DAAC.
- Open-Meteo.com (CC BY 4.0); GloFAS, Copernicus Emergency Management Service; ECMWF.
- Basemaps © CARTO, © OpenStreetMap contributors; satellite imagery © Esri, Maxar, Earthstar Geographics. Place search by OpenStreetMap Nominatim.
