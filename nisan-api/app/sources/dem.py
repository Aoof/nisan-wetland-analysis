"""Copernicus GLO-30 DEM + HAND for the basin (30 m, EPSG:32615), fetched by the API itself.

Both layers are public cloud-optimised GeoTIFFs on AWS Open Data (no login). GDAL range-reads only the
basin's part of each 1x1 degree tile, the result is put on the shared UTM 15N 30 m grid and cached in
DATA/dem. Terrain does not change, so the download happens once; delete DATA/dem to rebuild.

Tiles are cut straight from these GeoTIFFs by rio-tiler, which reprojects them exactly; a 100 m copy on
the shared AOI grid backs the zone statistics (sea mask, HAND shares).
"""
import math
from functools import lru_cache

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject

from .. import geo
from ..settings import BBOX, DATA
from ..store import set_status

DIR = DATA / "dem"
HAND_CLASS = DIR / "coatzacoalcos_hand_class_utm15n.tif"
HAND_M = DIR / "coatzacoalcos_hand_utm15n.tif"
DEM_M = DIR / "coatzacoalcos_dem_utm15n.tif"

DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif"
HAND_URL = "https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_{tile}_HAND.tif"
HAND_BREAKS = (1, 5, 15)  # m; common starting points, not calibrated
# Range reads over plain HTTPS; never list the S3 "directory" first.
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MAX_RETRY": "4", "GDAL_HTTP_RETRY_DELAY": "2"}

# 1: 0-1 m above drainage, 2: 1-5 m, 3: 5-15 m, 4: >15 m, 0: sea / no data
CLASSES = {
    1: ("0–1 m above river", "emergency", "barely above the nearest stream; it floods first"),
    2: ("1–5 m above river", "warning", "low ground near drainage; floods in bigger events"),
    3: ("5–15 m above river", "watch", "raised ground; floods only in extreme events"),
    4: ("over 15 m above river", "normal", "well above local drainage"),
}
COLORMAP = {1: (198, 40, 40, 130), 2: (217, 98, 43, 38)}


def version() -> str:
    """Changes when the terrain file or its colours change, so tile URLs can be cached forever."""
    import hashlib
    h = hashlib.md5(f"{HAND_CLASS.stat().st_mtime_ns}{sorted(COLORMAP.items())}".encode()).hexdigest()[:8]
    return h


def available() -> bool:
    return HAND_CLASS.exists() and HAND_M.exists() and DEM_M.exists()


@lru_cache(maxsize=1)
def grids() -> dict[str, np.ndarray]:
    """HAND class, HAND metres and elevation on the AOI grid."""
    t, w, h = geo.aoi_grid()
    out = {}
    for key, path, res, dtype in (("cls", HAND_CLASS, Resampling.nearest, "uint8"), ("hand", HAND_M, Resampling.bilinear, "float32"), ("dem", DEM_M, Resampling.bilinear, "float32")):
        with rasterio.open(path) as src:
            dst = np.full((h, w), 0 if dtype == "uint8" else np.nan, dtype=dtype)
            reproject(rasterio.band(src, 1), dst, src_nodata=src.nodata, dst_nodata=0 if dtype == "uint8" else np.nan,
                      dst_transform=t, dst_crs="EPSG:3857", resampling=res)
            out[key] = dst
    return out


def land_mask() -> np.ndarray:
    return grids()["cls"] > 0


_to_utm = Transformer.from_crs(4326, 32615, always_xy=True)


def point(lon: float, lat: float) -> dict | None:
    """Exact 30 m values at a point (sampled in the source UTM grid)."""
    if not available():
        return None
    x, y = _to_utm.transform(lon, lat)
    with rasterio.open(HAND_CLASS) as c, rasterio.open(HAND_M) as hm, rasterio.open(DEM_M) as d:
        if not (c.bounds.left <= x <= c.bounds.right and c.bounds.bottom <= y <= c.bounds.top):
            return None
        cls = int(next(c.sample([(x, y)]))[0])
        hand = float(next(hm.sample([(x, y)]))[0])
        dem = float(next(d.sample([(x, y)]))[0])
    if cls == 0:
        return {"cls": 0, "hand_m": None, "elevation_m": None}
    return {"cls": cls, "hand_m": round(hand, 2), "elevation_m": round(dem, 1)}


def class_shares(lon: float, lat: float, radius_km: float) -> dict[int, float]:
    """Share of land cells in each HAND class within a radius of a point."""
    g = grids()["cls"]
    t, w, h = geo.aoi_grid()
    x, y = geo.to_mercator(lon, lat)
    r = radius_km * 1000 / np.cos(np.deg2rad(lat))
    c0, c1 = max(0, int((x - r - t.c) // geo.RES)), min(w, int((x + r - t.c) // geo.RES) + 1)
    r0, r1 = max(0, int((t.f - (y + r)) // geo.RES)), min(h, int((t.f - (y - r)) // geo.RES) + 1)
    cc, rr = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
    cx, cy = t.c + (cc + 0.5) * geo.RES, t.f - (rr + 0.5) * geo.RES
    inside = (cx - x) ** 2 + (cy - y) ** 2 <= r * r
    vals = g[r0:r1, c0:c1][inside]
    vals = vals[(vals >= 1) & (vals <= 4)]
    n = len(vals) or 1
    return {k: float((vals == k).sum()) / n for k in (1, 2, 3, 4)}


def tile_names(bbox=BBOX):
    """1x1 degree tile names (SW corner) covering the box, e.g. N17_00_W095_00."""
    w, s, e, n = bbox
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            yield f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00"


def _mosaic_to_grid(template: str) -> tuple[np.ndarray, float]:
    """Basin cut of a tiled COG layer on the shared UTM 30 m grid. Missing tiles (open sea) are skipped."""
    srcs = []
    for t in tile_names():
        try:
            srcs.append(rasterio.open("/vsicurl/" + template.format(tile=t)))
        except rasterio.errors.RasterioIOError:
            continue  # no tile over open sea
    if not srcs:
        raise RuntimeError(f"no tiles found for {BBOX}")
    try:
        nodata = srcs[0].nodata if srcs[0].nodata is not None else -9999.0
        pad = 0.02  # a margin so the reprojection has neighbours at the edges
        data, transform = merge(srcs, bounds=(BBOX[0] - pad, BBOX[1] - pad, BBOX[2] + pad, BBOX[3] + pad), nodata=nodata)
        crs = srcs[0].crs
    finally:
        for s in srcs:
            s.close()
    t, w, h = geo.utm_grid(30)
    out = np.full((h, w), nodata, dtype="float32")
    reproject(data[0].astype("float32"), out, src_transform=transform, src_crs=crs, src_nodata=nodata,
              dst_transform=t, dst_crs=geo.UTM15N, dst_nodata=nodata, resampling=Resampling.bilinear)
    return out, float(nodata)


def classify(hand: np.ndarray, dem: np.ndarray, nodata: float) -> np.ndarray:
    """1 = 0-1 m, 2 = 1-5 m, 3 = 5-15 m, 4 = >15 m above drainage, 0 = sea or no data."""
    bad = ~np.isfinite(hand) | (hand == nodata)
    cls = (np.digitize(np.where(bad, 0, hand), HAND_BREAKS) + 1).astype("uint8")
    # The DEM sets the sea to 0 m and HAND is ~0 there too (resampling leaves ~1e-5); keep it out of "floods first".
    sea = (np.where(dem == nodata, 0, dem) <= 0) & (np.where(bad, 0, hand) < 0.01)
    cls[bad | sea] = 0
    return cls


def _write(path, arr: np.ndarray, nodata) -> None:
    t, w, h = geo.utm_grid(30)
    part = path.with_suffix(".part.tif")
    profile = {"driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": arr.dtype.name, "crs": geo.UTM15N,
               "transform": t, "nodata": nodata, "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256}
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(arr, 1)
    part.replace(path)


def build() -> None:
    """Download and cut both layers, then write the three GeoTIFFs. Class raster last: available() keys on all three."""
    DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(**GDAL_ENV):
        dem, nd = _mosaic_to_grid(DEM_URL)
        hand, nh = _mosaic_to_grid(HAND_URL)
    _write(DEM_M, dem, nd)
    _write(HAND_M, hand, nh)
    _write(HAND_CLASS, classify(hand, dem, nh), 0)


async def refresh() -> None:
    """Fetch once (cached forever), then load the 100 m grids the zone statistics use."""
    import asyncio
    if not available():
        set_status("dem-hand", "refreshing", "Downloading Copernicus GLO-30 elevation and HAND (one time, about a minute)")
        try:
            await asyncio.to_thread(build)
        except Exception as e:
            set_status("dem-hand", "error", f"Terrain download failed: {type(e).__name__}: {e}")
            return
    grids.cache_clear()
    await asyncio.to_thread(grids)
    set_status("dem-hand", "live", "Terrain layers ready")
