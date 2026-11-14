"""Fetch NISAR L2 GCOV for the AOI, classify water, and build an inundation history.

    python fetch_nisar.py                         # Oct 2025 – today, all tracks
    python fetch_nisar.py --start 2026-06-01 --workers 2
    python fetch_nisar.py --no-backscatter        # keep only the water classes (much smaller)
    python fetch_nisar.py --summarize-only        # rebuild summaries from existing outputs

Each GCOV file is ~6.5 GB. It is streamed over HTTPS and only the window over
the AOI is read, then averaged onto the shared UTM 15N 30 m grid. Every
acquisition is written as soon as it is done, so a rerun skips finished ones.

Outputs (data/processed/):
    acquisitions/<aoi>_nisar_<time>_<track><dir>_class.tif   0 no data, 1 not water, 2 open water, 3 flooded vegetation
    acquisitions/<aoi>_nisar_<time>_<track><dir>_db.tif      HH, HV backscatter (dB x 100, int16)
    <aoi>_nisar_summary.csv          per-acquisition water area and mean backscatter
    <aoi>_nisar_water_frequency.tif  band 1 open water, band 2 flooded vegetation, band 3 any water, band 4 observations
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import config
from grid import target_grid

DB_SCALE = 100
DB_NODATA = -32768
NAME_RE = re.compile(r"GCOV_(?P<cycle>\d{3})_(?P<track>\d{3})_(?P<dir>[AD])_(?P<frame>\d{3})_.*?_"
                     r"(?P<start>\d{8}T\d{6})_\d{8}T\d{6}_")


def parse_name(url):
    m = NAME_RE.search(Path(url).name)
    if not m:
        raise ValueError(f"unexpected GCOV name {Path(url).name}")
    return m.groupdict()


def out_paths(url):
    g = parse_name(url)
    stem = (config.OUT_DIR / "acquisitions" /
            f"{config.AOI_NAME}_nisar_{g['start']}_{g['track']}{g['dir']}_{g['frame']}")
    return Path(f"{stem}_class.tif"), Path(f"{stem}_db.tif")


def search():
    import earthaccess

    seen = {}
    for short_name in config.GCOV_COLLECTIONS:  # first collection wins on duplicates
        for g in earthaccess.search_data(short_name=short_name, bounding_box=config.BBOX,
                                         temporal=(ARGS.start, ARGS.end)):
            for u in g.data_links():
                if u.endswith(".h5"):
                    k = parse_name(u)
                    seen.setdefault((k["start"], k["track"], k["frame"]), u)
    return sorted(seen.values(), key=lambda u: parse_name(u)["start"])


def _require(h5, path):
    try:
        return h5[path]
    except KeyError:
        parent = path.rsplit("/", 1)[0]
        keys = list(h5[parent].keys()) if parent in h5 else list(h5.keys())
        raise KeyError(f"{path} not in file; {parent} holds: {keys}") from None


def read_window(h5):
    """Read HH and HV over the AOI window. Returns arrays, source transform, source CRS."""
    from pyproj import Transformer
    from rasterio.transform import from_origin

    grid = _require(h5, config.GCOV_GRID)
    epsg = int(np.asarray(_require(h5, f"{config.GCOV_GRID}/projection").attrs["epsg_code"]))
    x = grid["xCoordinates"][:]
    y = grid["yCoordinates"][:]
    w, s, e, n = config.BBOX
    xs, ys = Transformer.from_crs(4326, epsg, always_xy=True).transform([w, e, w, e], [s, s, n, n])
    cols = np.nonzero((x >= min(xs)) & (x <= max(xs)))[0]
    rows = np.nonzero((y >= min(ys)) & (y <= max(ys)))[0]
    if cols.size == 0 or rows.size == 0:
        return None
    c0, c1, r0, r1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    dx, dy = x[1] - x[0], y[1] - y[0]
    if dy > 0:
        raise RuntimeError("expected north-up GCOV grid (descending yCoordinates)")
    transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)

    bands = {}
    for term, name in (("HHHH", "hh"), ("HVHV", "hv")):
        if term in grid:
            bands[name] = grid[term][r0:r1, c0:c1].astype("float32")
    if "hh" not in bands:
        raise KeyError(f"no HHHH in {config.GCOV_GRID}; terms: {list(grid.keys())}")
    return bands, transform, f"EPSG:{epsg}"


def to_target(arr, src_transform, src_crs):
    from rasterio.warp import Resampling, reproject

    transform, width, height = target_grid()
    out = np.full((height, width), np.nan, "float32")
    arr = np.where(np.isfinite(arr) & (arr > 0), arr, np.nan)
    reproject(arr, out, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=transform, dst_crs=config.TARGET_CRS, dst_nodata=np.nan,
              resampling=Resampling.average)  # average in linear power, then dB
    return out


def classify(hh_db, hv_db):
    cls = np.zeros(hh_db.shape, "uint8")
    valid = np.isfinite(hh_db)
    cls[valid] = 1
    cls[valid & (hh_db < config.OPEN_WATER_HH_MAX_DB)] = 2
    if hv_db is not None:
        fv = valid & (hh_db > config.FLOODED_VEG_HH_MIN_DB) & (hh_db - hv_db > config.FLOODED_VEG_HH_HV_MIN_DB)
        cls[fv] = 3
    return cls


def write_outputs(url, hh_db, hv_db, keep_backscatter):
    import rasterio

    transform, width, height = target_grid()
    profile = {"driver": "GTiff", "crs": config.TARGET_CRS, "transform": transform,
               "width": width, "height": height, "compress": "deflate", "tiled": True}
    cls_path, db_path = out_paths(url)
    cls_path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backscatter:
        tmp = db_path.with_suffix(".tmp.tif")
        layers = [("HH_dB", hh_db)] + ([("HV_dB", hv_db)] if hv_db is not None else [])
        with rasterio.open(tmp, "w", **profile, count=len(layers), dtype="int16",
                           nodata=DB_NODATA) as dst:
            for i, (name, a) in enumerate(layers, 1):
                dst.write(np.where(np.isfinite(a), np.round(a * DB_SCALE), DB_NODATA).astype("int16"), i)
                dst.set_band_description(i, name)
            dst.scales = [1 / DB_SCALE] * len(layers)  # GIS tools then show plain dB
        tmp.rename(db_path)
    tmp = cls_path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile, count=1, dtype="uint8", nodata=0) as dst:
        dst.write(classify(hh_db, hv_db), 1)
        dst.update_tags(**{f"class_{k}": v for k, v in config.CLASSES.items()})
    tmp.rename(cls_path)  # written last: its presence marks the acquisition as done
    return cls_path


def process_h5(h5file, url, keep_backscatter):
    """Window, regrid, classify and write one GCOV file (path or file object)."""
    import h5py

    with h5py.File(h5file, "r") as h5:
        got = read_window(h5)
    if got is None:
        return None
    bands, src_t, src_crs = got
    with np.errstate(divide="ignore", invalid="ignore"):
        hh_db = 10 * np.log10(to_target(bands["hh"], src_t, src_crs))
        hv_db = 10 * np.log10(to_target(bands["hv"], src_t, src_crs)) if "hv" in bands else None
    return write_outputs(url, hh_db, hv_db, keep_backscatter)


def worker(url, keep_backscatter):
    if out_paths(url)[0].exists():
        return out_paths(url)[0]
    import os

    import earthaccess

    strategy = "environment" if os.environ.get("EARTHDATA_USERNAME") else "netrc"
    if not earthaccess.login(strategy=strategy).authenticated:
        raise RuntimeError("Earthdata login failed in worker")
    # Large blocks + cache: HDF5 makes many small reads, HTTPS round trips are slow.
    [f] = earthaccess.open([url], show_progress=False,
                           open_kwargs={"block_size": 8 * 2**20, "cache_type": "blockcache"})
    return process_h5(f, url, keep_backscatter)


def summarize():
    import pandas as pd
    import rasterio

    files = sorted((config.OUT_DIR / "acquisitions").glob(f"{config.AOI_NAME}_nisar_*_class.tif"))
    if not files:
        sys.exit("No classified acquisitions yet")
    sea = None
    if config.SEA_MASK.exists():
        with rasterio.open(config.SEA_MASK) as src:
            sea = src.read(1) == 0
        print(f"Using sea mask {config.SEA_MASK.name}")
    px_km2 = (config.TARGET_RES_M / 1000) ** 2
    rows, counts = [], None
    for f in files:
        with rasterio.open(f) as src:
            cls = src.read(1)
            profile = src.profile
        if sea is not None:
            cls = np.where(sea, 0, cls)
        if counts is None:
            counts = np.zeros((4,) + cls.shape, "uint16")
        counts[0] += cls == 2
        counts[1] += cls == 3
        counts[2] += cls >= 2
        counts[3] += cls > 0
        m = re.search(r"_nisar_(\d{8}T\d{6})_(\d{3})([AD])_(\d{3})_class", f.name)
        row = {"time": m.group(1), "track": m.group(2), "direction": m.group(3), "frame": m.group(4),
               "observed_fraction": float((cls > 0).mean()),
               "open_water_km2": float((cls == 2).sum() * px_km2),
               "flooded_vegetation_km2": float((cls == 3).sum() * px_km2)}
        db = Path(str(f).replace("_class.tif", "_db.tif"))
        if db.exists():
            with rasterio.open(db) as src:
                for i, name in enumerate(src.descriptions, 1):
                    a = src.read(i, masked=True).astype("float32") / DB_SCALE
                    if sea is not None:
                        a = np.ma.masked_where(sea, a)
                    row[f"{name}_mean"] = float(a.mean()) if a.count() else np.nan
        rows.append(row)

    stem = config.OUT_DIR / f"{config.AOI_NAME}_nisar"
    pd.DataFrame(rows).to_csv(f"{stem}_summary.csv", index=False)
    obs = counts[3]
    freq = np.where(obs > 0, counts[:3] / np.maximum(obs, 1), -1).astype("float32")
    profile.update(count=4, dtype="float32", nodata=-1)
    with rasterio.open(f"{stem}_water_frequency.tif", "w", **profile) as dst:
        dst.write(np.concatenate([freq, obs[None].astype("float32")]))
        for i, d in enumerate(["open_water", "flooded_vegetation", "any_water", "observations"], 1):
            dst.set_band_description(i, d)
    print(f"Wrote {stem}_summary.csv\nWrote {stem}_water_frequency.tif")


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=config.DEFAULT_START)
    ap.add_argument("--end", default=config.DEFAULT_END)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-backscatter", action="store_true", help="skip the HH/HV dB rasters")
    ap.add_argument("--summarize-only", action="store_true")
    ARGS = ap.parse_args()

    if not ARGS.summarize_only:
        import earthaccess

        if not earthaccess.login(persist=True).authenticated:
            sys.exit("Earthdata login failed")
        urls = search()
        if not urls:
            sys.exit(f"No GCOV over {config.BBOX} for {ARGS.start}..{ARGS.end}")
        todo = [u for u in urls if not out_paths(u)[0].exists()]
        print(f"{len(urls)} acquisitions, {len(todo)} to process")
        failed = []
        with ProcessPoolExecutor(ARGS.workers) as ex:
            futs = {ex.submit(worker, u, not ARGS.no_backscatter): u for u in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    fut.result()
                except Exception as e:
                    failed.append((futs[fut], e))
                print(f"\r{i}/{len(todo)} done, {len(failed)} failed", end="", flush=True)
        print()
        for u, e in failed[:5]:
            print(f"  failed {Path(u).name}: {e}", file=sys.stderr)
        if failed:
            print(f"{len(failed)} failed; rerun the same command to retry them.")
    summarize()


if __name__ == "__main__":
    main()
