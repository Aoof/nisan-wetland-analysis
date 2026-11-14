"""Fetch NASA OPERA Sentinel-1 / HLS products for the AOI and put each date on one shared grid.

    python fetch_opera.py dswx-s1                    # radar water masks (main one)
    python fetch_opera.py dswx-hls --start 2026-01-01
    python fetch_opera.py rtc-s1                     # VV/VH backscatter, larger downloads
    python fetch_opera.py dswx-s1 --skip-download    # reprocess what is already in data/raw

Only the needed layers are downloaded (the WTR water class, or the VV/VH bands),
then every tile or burst from the same day is mosaicked onto the shared
UTM 15N 30 m grid.

Outputs (data/processed/<product>/):
    <aoi>_<product>_<YYYYMMDD>.tif   one file per acquisition date
    <aoi>_<product>_summary.csv      per-date water area (DSWx) or mean dB (RTC)
    <aoi>_<product>_water_frequency.tif   DSWx only: share of observed dates each pixel was wet
"""
import argparse
import re
import sys
from collections import defaultdict

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

import config
from grid import target_grid

FILL = 255
VALID = sorted(config.DSWX_DRY | set(config.DSWX_WATER))


def sensing_date(name):
    m = re.search(r"_(\d{8})T\d{6}Z_", name)
    if not m:
        raise ValueError(f"no sensing time in {name}")
    return m.group(1)


def download(product, start, end):
    import earthaccess

    if not earthaccess.login(persist=True).authenticated:
        sys.exit("Earthdata login failed")
    p = config.PRODUCTS[product]
    granules = earthaccess.search_data(short_name=p["short_name"], bounding_box=config.BBOX,
                                       temporal=(start, end))
    urls = [u for g in granules for u in g.data_links() if any(u.endswith(s) for s in p["layers"])]
    if not urls:
        sys.exit(f"No {p['short_name']} files for {start}..{end}")
    raw = config.RAW_DIR / product
    raw.mkdir(parents=True, exist_ok=True)
    print(f"{len(granules)} granules, {len(urls)} files to fetch (existing files are skipped)")
    earthaccess.download(urls, local_path=str(raw))


def _warp(path, transform, width, height, resampling, dst_nodata, dtype):
    out = np.full((height, width), dst_nodata, dtype=dtype)
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=transform, dst_crs=config.TARGET_CRS,
                  resampling=resampling, src_nodata=src.nodata, dst_nodata=dst_nodata)
    return out


def mosaic_water(paths, transform, width, height):
    """Combine tiles of one date: a real class beats a mask code, which beats fill."""
    out = np.full((height, width), FILL, dtype="uint8")
    for p in paths:
        a = _warp(p, transform, width, height, Resampling.nearest, FILL, "uint8")
        have_valid = np.isin(out, VALID)
        take = ~have_valid & (a != FILL) & (np.isin(a, VALID) | (out == FILL))
        out[take] = a[take]
    return out


def mosaic_backscatter(paths, transform, width, height):
    out = np.full((height, width), np.nan, dtype="float32")
    for p in paths:
        a = _warp(p, transform, width, height, Resampling.bilinear, np.nan, "float32")
        take = np.isnan(out) & np.isfinite(a) & (a > 0)
        out[take] = a[take]
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(out)


def process(product):
    import pandas as pd

    p = config.PRODUCTS[product]
    files = sorted((config.RAW_DIR / product).glob("*.tif"))
    if not files:
        sys.exit(f"No files in {config.RAW_DIR / product}; run without --skip-download first")
    groups = defaultdict(lambda: defaultdict(list))  # date -> layer -> files
    for f in files:
        layer = next((s for s in p["layers"] if f.name.endswith(s)), None)
        if layer:
            groups[sensing_date(f.name)][layer].append(f)

    transform, width, height = target_grid()
    out_dir = config.OUT_DIR / product
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "GTiff", "crs": config.TARGET_CRS, "transform": transform,
               "width": width, "height": height, "compress": "deflate", "tiled": True}
    px_km2 = (config.TARGET_RES_M / 1000) ** 2
    rows = []
    wet_count = np.zeros((height, width), "uint16")
    obs_count = np.zeros((height, width), "uint16")

    for date in sorted(groups):
        out = out_dir / f"{config.AOI_NAME}_{product}_{date}.tif"
        if p["kind"] == "water":
            cls = mosaic_water(groups[date]["_B01_WTR.tif"], transform, width, height)
            with rasterio.open(out, "w", **profile, count=1, dtype="uint8", nodata=FILL) as dst:
                dst.write(cls, 1)
            observed = np.isin(cls, VALID)
            wet = np.isin(cls, list(config.DSWX_WATER))
            obs_count += observed
            wet_count += wet
            row = {"date": date, "observed_fraction": observed.mean(), "water_km2": wet.sum() * px_km2}
            for code, label in config.DSWX_WATER.items():
                row[f"{label.split(' (')[0].replace(' ', '_')}_km2"] = (cls == code).sum() * px_km2
        else:
            bands = [mosaic_backscatter(groups[date][s], transform, width, height) for s in p["layers"]]
            with rasterio.open(out, "w", **profile, count=len(bands), dtype="float32", nodata=np.nan) as dst:
                for i, (b, s) in enumerate(zip(bands, p["layers"]), 1):
                    dst.write(b, i)
                    dst.set_band_description(i, s[1:-4] + "_dB")
            row = {"date": date}
            for b, s in zip(bands, p["layers"]):
                pol = s[1:-4]
                row[f"{pol}_mean_dB"] = float(np.nanmean(b)) if np.isfinite(b).any() else np.nan
                row[f"{pol}_coverage"] = float(np.isfinite(b).mean())
        rows.append(row)
        print(f"  {date}: {out.name}")

    stem = out_dir / f"{config.AOI_NAME}_{product}"
    pd.DataFrame(rows).to_csv(f"{stem}_summary.csv", index=False)
    print(f"Wrote {stem}_summary.csv")
    if p["kind"] == "water":
        freq = np.where(obs_count > 0, wet_count / np.maximum(obs_count, 1), -1).astype("float32")
        with rasterio.open(f"{stem}_water_frequency.tif", "w", **profile, count=2,
                           dtype="float32", nodata=-1) as dst:
            dst.write(freq, 1)
            dst.write(obs_count.astype("float32"), 2)
            dst.set_band_description(1, "water_frequency")
            dst.set_band_description(2, "observed_dates")
        print(f"Wrote {stem}_water_frequency.tif")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("product", choices=sorted(config.PRODUCTS))
    ap.add_argument("--start", default=config.DEFAULT_START)
    ap.add_argument("--end", default=config.DEFAULT_END)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    if not args.skip_download:
        download(args.product, args.start, args.end)
    process(args.product)


if __name__ == "__main__":
    main()
