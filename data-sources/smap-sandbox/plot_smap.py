"""Plot an AOI cube from fetch_smap.py: mean time series plus a map of the period mean.

    python plot_smap.py data/processed/coatzacoalcos_l4_2025-11-01_2026-10-31.nc
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xarray as xr

PRIMARY = {"l3": ["soil_moisture_am", "soil_moisture_pm"],
           "l4": ["sm_surface", "sm_rootzone"]}


def main(path):
    ds = xr.open_dataset(path, engine="h5netcdf")
    product = "l3" if "soil_moisture_am" in ds else "l4"
    variables = PRIMARY[product]

    fig, (ax_ts, ax_map) = plt.subplots(1, 2, figsize=(13, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    for v in variables:
        ds[v].mean(["lat", "lon"]).plot(ax=ax_ts, label=v, marker="." if product == "l3" else None, lw=1)
    ax_ts.set_ylabel("soil moisture (m³/m³)")
    ax_ts.set_title(f"{ds.attrs.get('aoi', '')}: AOI mean")
    ax_ts.legend()

    ds[variables[-1]].mean("time").plot(ax=ax_map, cmap="YlGnBu", cbar_kwargs={"label": "m³/m³"})
    ax_map.set_title(f"{variables[-1]}, period mean")
    ax_map.set_aspect("equal")

    fig.tight_layout()
    out = Path(path).with_suffix(".png")
    fig.savefig(out, dpi=130)
    print(f"Wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
