# copernicus-dem-sandbox

Elevation and **HAND** (Height Above Nearest Drainage) for Coatzacoalcos. HAND is how far a cell sits above the stream it drains into, so low-HAND cells are the ones that flood first. Both layers come from the Copernicus GLO-30 30 m DEM, published as public files on AWS. No login is needed.

## Setup and run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python fetch_dem.py
```

The run takes about a minute.

## Outputs (`data/processed/`)

- `*_dem.tif` and `*_hand.tif`: clipped to the AOI on the native 1 arc-second grid.
- `*_dem_utm15n.tif`, `*_hand_utm15n.tif` and `*_hand_class_utm15n.tif`: on the **shared UTM 15N 30 m grid** that the Sentinel and NISAR sandboxes also use.
- HAND classes: 1 = 0–1 m, 2 = 1–5 m, 3 = 5–15 m, 4 = over 15 m, 0 = sea or no data.
- `*_dem_hand.png`: a quick-look map.

**Run this sandbox first.** The NISAR sandbox reads `*_hand_class_utm15n.tif` as a sea mask, so the Gulf isn't counted as open water.

## Caveats

- **Surface heights, not ground.** GLO-30 measures the top surface (from radar data taken in 2011–2015), so in towns and forest it gives the height of roofs and canopy, not the ground. Heights are relative to the EGM2008 geoid, not to local benchmarks.
- **Unvalidated class breaks.** The HAND breaks (1/5/15 m) are generic starting points. Check them against past flood extents before using them as risk classes.
- **Approximate sea mask.** The sea is detected as elevation ≤ 0 m with HAND ≈ 0, so coastal lagoons at 0 m are masked too.
