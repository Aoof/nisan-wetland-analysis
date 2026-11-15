"""Shared grid and projection helpers.

Every raster the API serves is first put on one Web Mercator grid ("the AOI grid",
100 m cells) and is then cut into XYZ tiles by rio-tiler. Nothing is placed by
interpolating corners in the browser.
"""
import math
from functools import lru_cache

import mgrs as _mgrs
import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin

from .settings import BBOX

RES = 100.0  # metres per cell in EPSG:3857
PAD = 2000.0
TILE_SIZE_M = 109_800  # Sentinel-2 / OPERA MGRS tile
TILE_SQUARE_M = 100_000

_to_m = Transformer.from_crs(4326, 3857, always_xy=True)
_to_ll = Transformer.from_crs(3857, 4326, always_xy=True)


def to_mercator(lon, lat):
    return _to_m.transform(lon, lat)


def to_lonlat(x, y):
    return _to_ll.transform(x, y)


@lru_cache(maxsize=1)
def aoi_grid():
    """(transform, width, height) of the shared AOI grid in EPSG:3857."""
    w, s, e, n = BBOX
    x0, y0 = to_mercator(w, s)
    x1, y1 = to_mercator(e, n)
    x0, y0, x1, y1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
    x0 = math.floor(x0 / RES) * RES
    y1 = math.ceil(y1 / RES) * RES
    width = math.ceil((x1 - x0) / RES)
    height = math.ceil((y1 - y0) / RES)
    return from_origin(x0, y1, RES, RES), width, height


@lru_cache(maxsize=1)
def cell_area_km2() -> np.ndarray:
    """True ground area of each AOI-grid row (Mercator stretches by 1/cos(lat)), shape (height,)."""
    t, _w, h = aoi_grid()
    ys = t.f - (np.arange(h) + 0.5) * RES
    lat = np.deg2rad([to_lonlat(0, y)[1] for y in ys])
    return ((RES * np.cos(lat)) ** 2 / 1e6).astype("float64")


def xy_to_cell(lon: float, lat: float):
    t, w, h = aoi_grid()
    x, y = to_mercator(lon, lat)
    c = int((x - t.c) // RES)
    r = int((t.f - y) // RES)
    return (r, c) if 0 <= r < h and 0 <= c < w else None


def lonlat_grid():
    """lon and lat of every cell centre on the AOI grid: (h, w) arrays."""
    t, w, h = aoi_grid()
    xs = t.c + (np.arange(w) + 0.5) * RES
    ys = t.f - (np.arange(h) + 0.5) * RES
    lon, _ = to_lonlat(xs, np.full_like(xs, ys[0]))
    _, lat = to_lonlat(np.full_like(ys, xs[0]), ys)
    return lon, lat  # lon varies by column only; lat by row only


@lru_cache(maxsize=64)
def mgrs_tile_origin(tile: str):
    """(zone, x0, y0) UTM lower-left corner of a 109.8 km MGRS tile like '15QUV'.

    Sentinel-2 / OPERA tiles are anchored at the NORTH-WEST corner of their 100 km
    MGRS square and extend 109.8 km east and south. The `mgrs` package returns the
    *centre* of the square, so: SW corner = centre - 50 km; tile lower-left =
    (SW.x, SW.y + 100 km - 109.8 km).

    CMR's bounding rectangles for these granules are NOT the nominal tile (they sit
    4.9 km off in both axes), so this was settled against the DEM instead: rivers in
    the water maps must lie in DEM valleys (tests/test_alignment.py). That test is
    sharp to about 300 m.
    """
    lat, lon = _mgrs.MGRS().toLatLon(tile)
    zone = int(tile[:2])
    t = Transformer.from_crs(4326, f"+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs", always_xy=True)
    cx, cy = t.transform(lon, lat)
    sw_x, sw_y = cx - TILE_SQUARE_M / 2, cy - TILE_SQUARE_M / 2
    return zone, sw_x, sw_y + TILE_SQUARE_M - TILE_SIZE_M


def utm_crs(zone: int) -> str:
    return f"+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs"
