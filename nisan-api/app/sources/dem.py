"""Copernicus GLO-30 DEM + HAND from data-sources/copernicus-dem-sandbox (30 m, EPSG:32615).

Tiles are cut straight from the sandbox GeoTIFFs by rio-tiler, which reprojects them
exactly; a 100 m copy on the shared AOI grid backs the zone statistics (sea mask, HAND shares).
"""
from functools import lru_cache

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.warp import Resampling, reproject

from .. import geo
from ..settings import SANDBOXES

PROCESSED = SANDBOXES / "copernicus-dem-sandbox" / "data" / "processed"
HAND_CLASS = PROCESSED / "coatzacoalcos_hand_class_utm15n.tif"
HAND_M = PROCESSED / "coatzacoalcos_hand_utm15n.tif"
DEM_M = PROCESSED / "coatzacoalcos_dem_utm15n.tif"

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
