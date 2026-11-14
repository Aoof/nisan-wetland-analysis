# sentintel-sandbox

Sentinel-1 (radar) and Harmonized Landsat/Sentinel-2 (HLS, optical) products for Coatzacoalcos, through **NASA OPERA**. OPERA products are already terrain-corrected and classified, so no SAR processing is needed. There is a pass every few days. The default date range is set in `config.py`.

| Key | Product | Use |
|---|---|---|
| `dswx-s1` | `OPERA_L3_DSWX-S1_V1` | Water maps from radar that see through cloud: open water and inundated vegetation. **Start here.** |
| `dswx-hls` | `OPERA_L3_DSWX-HLS_V1` | Water maps from optical imagery. Includes partial surface water, but cloud blocks it. |
| `rtc-s1` | `OPERA_L2_RTC-S1_V1` | VV/VH backscatter, for your own classification or to compare with NISAR. |

## Setup and run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python fetch_opera.py dswx-s1
.venv/bin/python fetch_opera.py dswx-s1 --skip-download   # re-mosaic without downloading
```

You need a NASA Earthdata login. The first run prompts for it and saves `~/.netrc`.

## Outputs (`data/processed/<product>/`)

- **One GeoTIFF per date** on the shared UTM 15N 30 m grid. All tiles or bursts from that day are merged.
- **`*_summary.csv`:** water area in km² per date and the share of the AOI observed (DSWx), or mean dB and coverage (RTC).
- **`*_water_frequency.tif` (DSWx only):**
  - Band 1 is the share of observed dates each pixel was wet.
  - Band 2 is how many dates observed it.
  - Use this to check the NISAR maps.

## Caveats

- **Download sizes.** WTR tiles are about 1 MB each. RTC bursts are about 13 MB each, and many overlap the AOI, so expect GBs per year for `rtc-s1`.
- **DSWx mask codes.** Values 250–255 (HAND-masked, layover/shadow, cloud, ocean, fill) count as *not observed*, not as dry. Steep slopes are masked by OPERA's own HAND filter.
- **Partial coverage.** Some dates cover only part of the AOI. Check `observed_fraction` before comparing water areas between dates.
- **Folder name.** The folder is spelled `sentintel-sandbox` in the repo. It is kept as-is so existing paths still work.
