"""Fetch SWOT 100 m water-surface rasters for the AOI as a (time, y, x) cube.

    python fetch_swot.py
    python fetch_swot.py --start 2026-01-01 --workers 2

Each raster tile is streamed and cut to the AOI, then placed on the shared
UTM 15N grid at 100 m. Every pass is cached, so a rerun resumes.

Outputs (data/processed/):
    <aoi>_swot_<start>_<end>.nc    wse (m), wse_uncert, wse_qual, water_frac, water_area (m2)
    <aoi>_swot_<start>_<end>.csv   per pass: median water surface elevation and water area
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
from grid import target_grid

NAME_RE = re.compile(r"_(?P<cycle>\d{3})_(?P<pass>\d{3})_(?P<scene>\d{3}[FR])_(?P<start>\d{8}T\d{6})_")


def parse_name(name):
    m = NAME_RE.search(name)
    if not m:
        raise ValueError(f"unexpected SWOT raster name {name}")
    return m.groupdict()


def target_coords():
    transform, width, height = target_grid(config.TARGET_RES_M)
    res = config.TARGET_RES_M
    x = transform.c + res / 2 + res * np.arange(width)
    y = transform.f - res / 2 - res * np.arange(height)
    return x, y


def subset_to_grid(ds):
    """Cut an opened raster Dataset to the AOI and snap it onto the shared grid."""
    x, y = target_coords()
    res = config.TARGET_RES_M
    sub = ds[config.VARIABLES].sel(x=slice(x.min() - res, x.max() + res))
    ysl = slice(y.max() + res, y.min() - res) if sub.y[0] > sub.y[-1] else slice(y.min() - res, y.max() + res)
    sub = sub.sel(y=ysl)
    if sub.sizes["x"] == 0 or sub.sizes["y"] == 0:
        return None
    sub = sub.reindex(x=x, y=y, method="nearest", tolerance=res / 2)
    out = {v: sub[v].values.astype("float32") for v in config.VARIABLES}
    if not np.isfinite(out["wse"]).any():
        return None
    return out


def worker(url, cache_dir):
    path = Path(cache_dir) / (Path(url).stem + ".npz")
    empty = path.with_suffix(".empty")
    if path.exists() or empty.exists():
        return path if path.exists() else None
    import earthaccess
    import xarray as xr

    strategy = "environment" if (os.environ.get("EARTHDATA_USERNAME") or os.environ.get("EARTHDATA_TOKEN")) else "netrc"
    if not earthaccess.login(strategy=strategy).authenticated:
        raise RuntimeError("Earthdata login failed in worker")
    [f] = earthaccess.open([url], show_progress=False)
    with xr.open_dataset(f, engine="h5netcdf", mask_and_scale=True) as ds:
        out = subset_to_grid(ds)
    if out is None:
        empty.touch()  # tile touches the bbox but has no water data inside it
        return None
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **out)
    tmp.rename(path)
    return path


def assemble(paths, start, end):
    import pandas as pd
    import xarray as xr

    x, y = target_coords()
    # Adjacent scenes of one pass can both overlap the AOI: merge them into one time step.
    passes = {}
    for p in sorted(paths, key=lambda p: parse_name(p.name)["start"]):
        m = parse_name(p.name)
        d = dict(np.load(p))
        key = (m["cycle"], m["pass"])
        if key not in passes:
            passes[key] = (m, d)
            continue
        merged = passes[key][1]
        fill = ~np.isfinite(merged["wse"]) & np.isfinite(d["wse"])
        for v in config.VARIABLES:
            merged[v][fill] = d[v][fill]
    meta = [m for m, _ in passes.values()]
    loaded = [d for _, d in passes.values()]
    times = [datetime.strptime(m["start"], "%Y%m%dT%H%M%S") for m in meta]
    ds = xr.Dataset(
        {v: (("time", "y", "x"), np.stack([d[v] for d in loaded])) for v in config.VARIABLES},
        coords={"time": times, "y": y, "x": x,
                "cycle": ("time", [int(m["cycle"]) for m in meta]),
                "pass": ("time", [int(m["pass"]) for m in meta])},
    )
    ds.attrs.update(aoi=config.AOI_NAME, crs=config.TARGET_CRS, source=f"NASA/CNES SWOT {config.SHORT_NAME} (PO.DAAC)")

    good = (ds.wse_qual <= config.MAX_WSE_QUAL) & (ds.water_frac >= config.MIN_WATER_FRAC)
    summary = pd.DataFrame({
        "cycle": ds.cycle.values, "pass": ds["pass"].values,
        "wse_median_m": ds.wse.where(good).median(["y", "x"]).values,
        "wse_p10_m": ds.wse.where(good).quantile(0.1, ["y", "x"]).values,
        "wse_p90_m": ds.wse.where(good).quantile(0.9, ["y", "x"]).values,
        "water_area_km2": (ds.water_area.where(ds.wse_qual <= config.MAX_WSE_QUAL).sum(["y", "x"]) / 1e6).values,
        "good_water_pixels": good.sum(["y", "x"]).values,
    }, index=pd.Index(times, name="time"))

    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = config.OUT_DIR / f"{config.AOI_NAME}_swot_{start}_{end}"
    enc = {v: {"zlib": True, "complevel": 4} for v in config.VARIABLES}
    ds.to_netcdf(f"{stem}.nc", engine="h5netcdf", encoding=enc)
    summary.to_csv(f"{stem}.csv")
    return Path(f"{stem}.nc"), Path(f"{stem}.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=config.DEFAULT_START)
    ap.add_argument("--end", default=config.DEFAULT_END)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    import earthaccess

    if not earthaccess.login(persist=True).authenticated:
        sys.exit("Earthdata login failed")
    granules = earthaccess.search_data(short_name=config.SHORT_NAME, bounding_box=config.BBOX,
                                       temporal=(args.start, args.end))
    urls = [u for g in granules for u in g.data_links()
            if u.endswith(".nc") and config.UTM_ZONE_TAG in Path(u).name]
    if not urls:
        sys.exit(f"No {config.SHORT_NAME} tiles for {args.start}..{args.end}")
    cache = config.CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    print(f"{len(urls)} raster tiles")

    paths, failed = [], []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = {ex.submit(worker, u, str(cache)): u for u in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                p = fut.result()
                if p:
                    paths.append(p)
            except Exception as e:
                failed.append((futs[fut], e))
            print(f"\r{i}/{len(urls)} done, {len(paths)} with data, {len(failed)} failed", end="", flush=True)
    print()
    for u, e in failed[:5]:
        print(f"  failed {Path(u).name}: {e}", file=sys.stderr)
    if not paths:
        sys.exit("No tiles had water data inside the AOI")
    nc, csv = assemble(paths, args.start, args.end)
    print(f"Wrote {nc}\nWrote {csv}")
    if failed:
        print(f"{len(failed)} tiles failed; rerun the same command to retry them.")


if __name__ == "__main__":
    main()
