# nisar-sandbox

NISAR L-band radar over Coatzacoalcos: water classes for each acquisition, and an inundation history built from them. NISAR's L-band signal penetrates vegetation, which lets it map **flooded vegetation** (water under mangroves and swamp forest), not only open water.

Source: `NISAR_L2_GCOV_V1` (validated) and `NISAR_L2_GCOV_PROVISIONAL_V1` (the earlier record), both from ASF. In November 2026 a search over the AOI returned 82 provisional and 7 V1 granules. Where both versions exist for one acquisition, the V1 is kept.

## Setup and run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python fetch_nisar.py                     # Oct 2025 to today
.venv/bin/python fetch_nisar.py --no-backscatter    # classes only, about 10x less disk
.venv/bin/python fetch_nisar.py --summarize-only    # rebuild CSV/frequency after tuning
```

- **Login:** you need a NASA Earthdata login. The first run prompts for it and saves `~/.netrc`.
- **Sea mask:** run the `copernicus-dem-sandbox` first so the summaries can mask out the Gulf.

## Outputs (`data/processed/`)

- **`acquisitions/*_class.tif`:** 1 = not water, 2 = open water, 3 = flooded vegetation, 0 = no data. These are on the shared UTM 15N 30 m grid, so they line up with OPERA DSWx and HAND.
- **`acquisitions/*_db.tif`:** HH and HV backscatter in dB, stored as int16 × 100 with the scale set in the file, so GIS tools display plain dB.
- **`*_nisar_summary.csv`:** open-water and flooded-vegetation area in km², plus mean dB, for each acquisition.
- **`*_nisar_water_frequency.tif`:** the share of observations that were open water, flooded vegetation, or either, plus an observation count.

## Caveats

- **Large files.** Each GCOV file is about 6.5 GB. The script streams it and reads only the AOI window, but each acquisition still pulls hundreds of MB over HTTPS. Use `--workers` sparingly. A run that is stopped resumes where it left off.
- **Untuned thresholds.** The classification thresholds in `config.py` are generic L-band starting points. Tune them against the OPERA DSWx water frequency and known wetlands before publishing maps. After changing them, delete `acquisitions/*_class.tif` and rerun; the `--summarize-only` flag does not reclassify.
- **Not yet run on a real file.** The reader follows the published GCOV layout (`/science/LSAR/GCOV/grids/frequencyA/HHHH`, `HVHV`, `xCoordinates`, `yCoordinates`, `projection`), but the scripts were tested only on synthetic files. If the layout differs, the error lists the groups the file actually has.
- **Mixed product versions.** Provisional products may be reprocessed. Keep their dates in mind when comparing them with V1.
- **Not handled yet:** wind-roughened open water can look like land, and so can urban double-bounce.
- **Soil moisture.** NISAR also publishes a soil-moisture product (`NISAR_L3_SME2_*`) at ASF, but this sandbox doesn't fetch it yet.
