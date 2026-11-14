"""Fetch Copernicus GLO-30 elevation and HAND for the AOI, clipped and on the shared grid.

    python fetch_dem.py

Outputs (data/processed/):
    <aoi>_dem.tif              elevation (m, EGM2008), native 1 arc-second grid
    <aoi>_hand.tif             height above nearest drainage (m), native grid
    <aoi>_dem_utm15n.tif       elevation on the shared UTM 15N 30 m grid
    <aoi>_hand_utm15n.tif      HAND on the shared grid
    <aoi>_hand_class_utm15n.tif  HAND classes (1 = 0-1 m, 2 = 1-5 m, 3 = 5-15 m, 4 = >15 m, 0 = sea or no data)
    <aoi>_dem_hand.png         quick-look map
"""
import math
import sys

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject

import config
from grid import target_grid


def tile_names(bbox):
    w, s, e, n = bbox
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
            yield f"{ns}_00_{ew}_00"


def mosaic(url_template, out_path):
    """Stream the tiles over HTTP (COG range reads) and clip to the AOI."""
    sources = []
    for tile in tile_names(config.BBOX):
        url = url_template.format(tile=tile)
        try:
            sources.append(rasterio.open(f"/vsicurl/{url}"))
        except rasterio.errors.RasterioIOError:
            print(f"  no tile {tile} (all sea), skipping")
    if not sources:
        sys.exit(f"No tiles found for {config.BBOX}")
    nodata = sources[0].nodata if sources[0].nodata is not None else -9999.0
    data, transform = merge(sources, bounds=config.BBOX, nodata=nodata)
    profile = sources[0].profile | {
        "driver": "GTiff", "height": data.shape[1], "width": data.shape[2],
        "transform": transform, "nodata": nodata, "compress": "deflate", "tiled": True,
    }
    for src in sources:
        src.close()
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data)
    return out_path


def to_shared_grid(src_path, out_path, resampling=Resampling.bilinear):
    with rasterio.open(src_path) as src:
        transform, width, height = target_grid()
        profile = src.profile | {"crs": config.TARGET_CRS, "transform": transform,
                                 "width": width, "height": height}
        with rasterio.open(out_path, "w", **profile) as dst:
            reproject(rasterio.band(src, 1), rasterio.band(dst, 1),
                      dst_transform=transform, dst_crs=config.TARGET_CRS,
                      resampling=resampling, dst_nodata=src.nodata)
    return out_path


def classify_hand(hand_path, dem_path, out_path):
    with rasterio.open(hand_path) as src:
        hand = src.read(1, masked=True)
        profile = src.profile | {"dtype": "uint8", "nodata": 0}
    with rasterio.open(dem_path) as src:
        dem = src.read(1, masked=True)
    breaks = list(config.HAND_CLASSES[1:])
    classes = (np.digitize(hand.filled(np.nan), breaks) + 1).astype("uint8")
    # The DEM sets the sea to 0 m, and HAND is 0 there too; keep it out of
    # "floods first". Coastal lagoons at exactly 0 m are masked as well.
    sea = (dem.filled(0) <= 0) & (hand.filled(0) < 0.01)  # resampling leaves ~1e-5 over the sea
    classes[np.ma.getmaskarray(hand) | ~np.isfinite(hand.filled(np.nan)) | sea] = 0
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(classes, 1)
    return out_path


def quicklook(dem_path, hand_path, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, path, title, cmap, vmax in (
            (axes[0], dem_path, "Elevation (m), capped at 100", "terrain", 100),
            (axes[1], hand_path, "HAND (m), capped at 20", "Blues_r", 20)):
        with rasterio.open(path) as src:
            a = src.read(1, masked=True)
            b = src.bounds
        im = ax.imshow(a, cmap=cmap, vmax=vmax, extent=(b.left, b.right, b.bottom, b.top))
        ax.set_title(title)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle(f"{config.AOI_NAME}: Copernicus GLO-30")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)


def main():
    out = config.OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stem = out / config.AOI_NAME
    print("Elevation tiles...")
    dem = mosaic(config.DEM_URL, f"{stem}_dem.tif")
    print("HAND tiles...")
    hand = mosaic(config.HAND_URL, f"{stem}_hand.tif")
    dem_u = to_shared_grid(dem, f"{stem}_dem_utm15n.tif")
    hand_u = to_shared_grid(hand, f"{stem}_hand_utm15n.tif")
    classify_hand(hand_u, dem_u, f"{stem}_hand_class_utm15n.tif")
    quicklook(dem_u, hand_u, f"{stem}_dem_hand.png")
    for p in sorted(out.glob(f"{config.AOI_NAME}_*")):
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
