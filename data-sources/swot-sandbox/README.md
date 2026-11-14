# swot-sandbox

SWOT water-surface **elevation** and water extent over Coatzacoalcos. SWOT measures the height of the water itself, not only where it is, so you can see the river and lagoons rising before they spread.

Source: `SWOT_L2_HR_Raster_100m_D` (100 m raster, latest processing) from PO.DAAC. SWOT passes over a given spot roughly every 21 days, with some overlap between passes.

## Setup and run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python fetch_swot.py
.venv/bin/python fetch_swot.py --start 2026-01-01 --workers 2
```

You need a NASA Earthdata login. The first run prompts for it and saves `~/.netrc`.

## Outputs (`data/processed/`)

- **`*_swot_<start>_<end>.nc`:** a `(time, y, x)` cube on the shared UTM 15N grid at 100 m. Variables:
  - `wse`: water surface elevation (m)
  - `wse_uncert`
  - `wse_qual`
  - `water_frac`
  - `water_area` (m²)

  Tiles from the same pass are merged into one time step.
- **`*_swot_<start>_<end>.csv`:** for each pass, the median and 10th/90th percentile water level of good-quality water pixels, the total water area, and a pixel count.

## Caveats

- **Quality filter.** The default keeps `wse_qual` 0–1 (good or suspect) and pixels at least 50% water. Both settings are in `config.py`.
- **AOI-wide summary.** The CSV mixes the river, lagoons and any coastal sea in the AOI. For a stage series at one place, take a small window from the `.nc`. SWOT's `RiverSP`/`LakeSP` products give per-reach and per-lake series, which this sandbox doesn't fetch yet.
- **Vegetation blocks the signal.** SWOT is Ka-band and doesn't see water under dense vegetation. NISAR covers that.
- **Elevation reference.** Heights are relative to the EGM2008 geoid, the same reference as the Copernicus DEM, so they can be compared directly with the DEM.
- **Not yet run on a real file.** The reader assumes 1-D `x`/`y` coordinates in the raster files. It was tested only on synthetic files.
