"""EASE-Grid 2.0 global 9 km (M09) grid used by SPL3SMP_E and SPL4SMGP.

The grid is a cylindrical equal-area projection (EPSG:6933), so each row has one
latitude and each column one longitude. That lets us turn a lat/lon box into
row/column slices and read only those cells from the global files.
"""
import math

import numpy as np
from pyproj import Transformer

CELL_M = 9008.055210146
NCOLS = 3856
NROWS = 1624
X0 = -CELL_M * NCOLS / 2  # west edge of column 0
Y0 = CELL_M * NROWS / 2   # north edge of row 0

_to_grid = Transformer.from_crs(4326, 6933, always_xy=True)
_to_geo = Transformer.from_crs(6933, 4326, always_xy=True)


def bbox_to_slices(bbox):
    """(W, S, E, N) degrees -> (row slice, col slice) covering the box."""
    w, s, e, n = bbox
    xw, yn = _to_grid.transform(w, n)
    xe, ys = _to_grid.transform(e, s)
    c0 = math.floor((xw - X0) / CELL_M)
    c1 = math.floor((xe - X0) / CELL_M) + 1
    r0 = math.floor((Y0 - yn) / CELL_M)
    r1 = math.floor((Y0 - ys) / CELL_M) + 1
    return slice(max(r0, 0), min(r1, NROWS)), slice(max(c0, 0), min(c1, NCOLS))


def cell_centers(rows, cols):
    """1-D latitude and longitude of cell centres for the given slices."""
    x = X0 + (np.arange(cols.start, cols.stop) + 0.5) * CELL_M
    y = Y0 - (np.arange(rows.start, rows.stop) + 0.5) * CELL_M
    lon, _ = _to_geo.transform(x, np.zeros_like(x))
    _, lat = _to_geo.transform(np.zeros_like(y), y)
    return np.asarray(lat), np.asarray(lon)
