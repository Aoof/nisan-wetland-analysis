# smap-sandbox

SMAP soil moisture for **Coatzacoalcos, Veracruz**: the lower Coatzacoalcos basin, including Minatitlán, the river floodplain and the Tonalá wetlands.
The bounding box is `(-94.90, 17.60, -94.00, 18.30)`, which is 10 × 11 cells on SMAP's 9 km grid. Edit `config.py` to change the area or dates.

| Key | Product | What it gives you |
|---|---|---|
| `l3` | `SPL3SMP_E` v006 | Daily satellite retrieval, 6 am and 6 pm passes. Top 5 cm of soil. Has gaps between swaths. |
| `l4` | `SPL4SMGP` v008 | Model plus satellite, every 3 hours, no gaps. Surface and **root-zone** moisture, wetness (0 = dry, 1 = saturated) and precipitation. |

L4 root-zone wetness is the better early sign of saturated ground and flood risk. L3 is the raw observation, useful for checking L4.

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

You need a free NASA Earthdata account (urs.earthdata.nasa.gov). The first run asks for your username and password and saves them to `~/.netrc`.
You can set `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` instead.

## Run

```bash
.venv/bin/python fetch_smap.py l4                       # Nov 2025 – Oct 2026, one granule per day
.venv/bin/python fetch_smap.py l3 --start 2024-01-01    # daily AM/PM retrievals
.venv/bin/python plot_smap.py data/processed/coatzacoalcos_l4_2025-11-01_2026-10-31.nc
```

- Files are streamed, and only the area's rows and columns are read. Full global granules are 145–650 MB, and none of them are downloaded.
- Each granule's subset is cached in `data/cache/`, so if a run is interrupted, running it again resumes.
- For L4, `--l4-time 133000` (07:30 local) keeps one granule per day. Pass `--l4-time all` for all eight per day, which takes 8× longer.

## Outputs (`data/processed/`, git-ignored)

- `<aoi>_<product>_<start>_<end>.nc` is a `(time, lat, lon)` cube with EASE-Grid 2.0 cell-centre coordinates.
- `<aoi>_<product>_<start>_<end>.csv` holds the area-average time series and a count of valid cells per date.
- `plot_smap.py` writes a `.png` next to the `.nc`, with the time series and a map of the period mean.

## Caveats

- **Quality flags.** L3 keeps every retrieval and adds `recommended_am/pm` masks (NASA's "recommended quality" bit). SMAP often flags wetland and coastal cells because of open water in the footprint, so the CSV includes means both with and without the mask. Check how many cells survive before you rely on the masked mean.
- **9 km cells.** A cell is about 81 km². Use this for regional trends and early signals, not for individual fields or streets. Field-scale detail will come from NISAR.
- **Gulf cells.** The northern edge of the box is sea, and those cells are always empty.
