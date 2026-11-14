"""Shared UTM 15N grid covering the AOI, so every date and product lines up pixel for pixel."""
import math

from pyproj import Transformer
from rasterio.transform import from_origin

import config


def target_grid(res=config.TARGET_RES_M):
    """(transform, width, height) of a grid snapped to `res` that covers BBOX."""
    w, s, e, n = config.BBOX
    t = Transformer.from_crs(4326, config.TARGET_CRS, always_xy=True)
    xs, ys = t.transform([w, e, w, e], [s, s, n, n])
    x0 = math.floor(min(xs) / res) * res
    y1 = math.ceil(max(ys) / res) * res
    width = math.ceil((max(xs) - x0) / res)
    height = math.ceil((y1 - min(ys)) / res)
    return from_origin(x0, y1, res, res), width, height
