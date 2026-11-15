"""Fetch SMAP soil moisture for the Coatzacoalcos AOI as a (time, lat, lon) cube.

Each global granule is streamed over HTTPS and only the rows and columns that
cover the AOI are read, so a 650 MB file costs a small fraction of that in
transfer. Every granule's subset is cached, so an interrupted run picks up
where it stopped.

    python fetch_smap.py l3                       # daily AM/PM retrievals
    python fetch_smap.py l4 --start 2026-06-01    # root-zone moisture, one granule a day
    python fetch_smap.py l4 --l4-time all         # all eight 3-hourly granules a day

Outputs go to data/processed/:
    <aoi>_<product>_<start>_<end>.nc    gridded cube
    <aoi>_<product>_<start>_<end>.csv   AOI-mean time series
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np

import config
from ease2 import bbox_to_slices, cell_centers

L4_VARS = (
    "sm_surface",                         # 0-5 cm, m3/m3
    "sm_rootzone",                        # 0-100 cm, m3/m3
    "sm_surface_wetness",                 # 0 = wilting point, 1 = saturated
    "sm_rootzone_wetness",
    "precipitation_total_surface_flux",   # kg m-2 s-1
)


def granule_time(name: str) -> datetime:
    m = re.search(r"_(\d{8})(?:T(\d{6}))?_", name)
    if not m:
        raise ValueError(f"no date in granule name {name}")
    return datetime.strptime(m.group(1) + (m.group(2) or "000000"), "%Y%m%d%H%M%S")


def _require(h5, path):
    try:
        return h5[path]
    except KeyError:
        parent = path.rsplit("/", 1)[0] if "/" in path else "/"
        keys = list(h5[parent].keys()) if parent in h5 else list(h5.keys())
        raise KeyError(f"{path} not in file; {parent} holds: {keys}") from None


def read_l3(h5, rows, cols):
    out = {}
    passes = (("am", "Soil_Moisture_Retrieval_Data_AM", ""),
              ("pm", "Soil_Moisture_Retrieval_Data_PM", "_pm"))
    for tag, group, sfx in passes:
        sm = _require(h5, f"{group}/soil_moisture{sfx}")[rows, cols].astype("float32")
        qf = _require(h5, f"{group}/retrieval_qual_flag{sfx}")[rows, cols]
        sm[sm < 0] = np.nan  # fill value is -9999
        out[f"soil_moisture_{tag}"] = sm
        # Bit 0 clear = NASA's "recommended quality". Wetland and coastal cells
        # are often flagged, so keep the raw value and store the flag separately.
        out[f"recommended_{tag}"] = ((qf & 1) == 0) & np.isfinite(sm)
    return out


def read_l4(h5, rows, cols, expected_lat):
    lat = _require(h5, "cell_lat")[rows, cols][:, 0]
    if not np.allclose(lat, expected_lat, atol=0.05):
        raise RuntimeError("EASE-Grid row mapping does not match the file's cell_lat")
    out = {}
    for v in L4_VARS:
        a = _require(h5, f"Geophysical_Data/{v}")[rows, cols].astype("float32")
        a[a < -9000] = np.nan
        out[v] = a
    return out


def _login(earthaccess):
    strategy = "environment" if (os.environ.get("EARTHDATA_USERNAME") or os.environ.get("EARTHDATA_TOKEN")) else "netrc"
    auth = earthaccess.login(strategy=strategy)
    if not auth.authenticated:
        raise RuntimeError("Earthdata login failed in worker")


def subset_granule(url, product, rows, cols, expected_lat, cache_dir):
    """Worker: stream one granule, read the AOI window, cache it as .npz."""
    path = Path(cache_dir) / (Path(url).stem + ".npz")
    if path.exists():
        return path
    import earthaccess
    import h5py

    _login(earthaccess)
    [fobj] = earthaccess.open([url], show_progress=False)
    with h5py.File(fobj, "r") as h5:
        arrays = read_l3(h5, rows, cols) if product == "l3" else read_l4(h5, rows, cols, expected_lat)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.rename(path)
    return path


def assemble(paths, product, rows, cols, start, end):
    import pandas as pd
    import xarray as xr

    lat, lon = cell_centers(rows, cols)
    paths = sorted(paths, key=lambda p: granule_time(p.name))
    times = [granule_time(p.name) for p in paths]
    loaded = [np.load(p) for p in paths]
    names = loaded[0].files
    ds = xr.Dataset(
        {k: (("time", "lat", "lon"), np.stack([d[k] for d in loaded])) for k in names},
        coords={"time": times, "lat": lat, "lon": lon},
    )
    p = config.PRODUCTS[product]
    ds.attrs.update(
        aoi=config.AOI_NAME,
        bbox_wsen=list(config.BBOX),
        source=f"NASA SMAP {p['short_name']} v{p['version']} (NSIDC DAAC)",
        grid="EASE-Grid 2.0 global 9 km (EPSG:6933), cell centres",
    )

    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = config.OUT_DIR / f"{config.AOI_NAME}_{product}_{start}_{end}"
    ds.to_netcdf(f"{stem}.nc", engine="h5netcdf")

    series = {}
    for k in names:
        if ds[k].dtype == bool:
            series[f"{k}_fraction"] = ds[k].mean(["lat", "lon"])
        else:
            series[f"{k}_mean"] = ds[k].mean(["lat", "lon"])
            series[f"{k}_valid_cells"] = ds[k].notnull().sum(["lat", "lon"])
    if product == "l3":
        for tag in ("am", "pm"):
            good = ds[f"soil_moisture_{tag}"].where(ds[f"recommended_{tag}"])
            series[f"soil_moisture_{tag}_recommended_mean"] = good.mean(["lat", "lon"])
    pd.DataFrame({k: v.to_series() for k, v in series.items()}).to_csv(f"{stem}.csv")
    return Path(f"{stem}.nc"), Path(f"{stem}.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("product", choices=sorted(config.PRODUCTS))
    ap.add_argument("--start", default=config.DEFAULT_START)
    ap.add_argument("--end", default=config.DEFAULT_END)
    ap.add_argument("--version", help="override the collection version in config.py")
    ap.add_argument("--l4-time", default="133000",
                    help="HHMMSS centre time (UTC) of the L4 granule to keep per day, or 'all' (default 133000 = 07:30 local)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    import earthaccess

    # First run prompts for your Earthdata username/password and saves ~/.netrc.
    if not earthaccess.login(persist=True).authenticated:
        sys.exit("Earthdata login failed")

    p = dict(config.PRODUCTS[args.product])
    if args.version:
        p["version"] = args.version
    granules = earthaccess.search_data(
        short_name=p["short_name"], version=p["version"],
        bounding_box=config.BBOX, temporal=(args.start, args.end),
    )
    urls = [u for g in granules for u in g.data_links() if u.endswith(".h5")]
    if args.product == "l4" and args.l4_time != "all":
        urls = [u for u in urls if f"T{args.l4_time}_" in Path(u).name]
    if not urls:
        sys.exit(f"No {p['short_name']} v{p['version']} granules for {args.start}..{args.end}")

    rows, cols = bbox_to_slices(config.BBOX)
    lat, _ = cell_centers(rows, cols)
    cache = config.CACHE_DIR / args.product
    cache.mkdir(parents=True, exist_ok=True)
    print(f"{len(urls)} granules, AOI window {rows.stop - rows.start}x{cols.stop - cols.start} cells")

    paths, failed = [], []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = {ex.submit(subset_granule, u, args.product, rows, cols, lat, str(cache)): u for u in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                paths.append(fut.result())
            except Exception as e:  # keep going; report at the end
                failed.append((futs[fut], e))
            print(f"\r{i}/{len(urls)} done, {len(failed)} failed", end="", flush=True)
    print()
    for url, e in failed[:5]:
        print(f"  failed {Path(url).name}: {e}", file=sys.stderr)
    if not paths:
        sys.exit("Nothing downloaded")

    nc, csv = assemble(paths, args.product, rows, cols, args.start, args.end)
    print(f"Wrote {nc}\nWrote {csv}")
    if failed:
        print(f"{len(failed)} granules failed; rerun the same command to retry them.")


if __name__ == "__main__":
    main()
