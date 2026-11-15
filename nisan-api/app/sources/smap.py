"""SMAP L4 soil moisture (SPL4SMGP, 9 km, model-assimilated, NSIDC) for the basin.

Each global granule is ~140 MB; only the basin's EASE-Grid rows and columns are read over HTTPS
(HDF5 range reads), and that small window is cached per granule as .npz. A refresh only reads
granules it has not cached yet. One granule a day is kept: the 13:30 UTC one (07:30 local).
"""
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Transformer

from ..settings import BBOX

SHORT = "SPL4SMGP"
VERSION = "008"
DAILY = "T133000"
VARS = {  # file variable -> series key
    "sm_rootzone_wetness": "rootzone_wetness",  # 0 = wilting point, 1 = saturated
    "sm_surface_wetness": "surface_wetness",
    "sm_rootzone": "rootzone_m3m3",
    "sm_surface": "surface_m3m3",
}

# EASE-Grid 2.0 global 9 km (EPSG:6933): one latitude per row, one longitude per column.
CELL_M = 9008.055210146
NCOLS, NROWS = 3856, 1624
X0, Y0 = -CELL_M * NCOLS / 2, CELL_M * NROWS / 2
_to_grid = Transformer.from_crs(4326, 6933, always_xy=True)
_to_geo = Transformer.from_crs(6933, 4326, always_xy=True)


def window(bbox=BBOX) -> tuple[slice, slice]:
    """(rows, cols) of the EASE-Grid cells covering the box."""
    w, s, e, n = bbox
    xw, yn = _to_grid.transform(w, n)
    xe, ys = _to_grid.transform(e, s)
    r0, r1 = math.floor((Y0 - yn) / CELL_M), math.floor((Y0 - ys) / CELL_M) + 1
    c0, c1 = math.floor((xw - X0) / CELL_M), math.floor((xe - X0) / CELL_M) + 1
    return slice(max(r0, 0), min(r1, NROWS)), slice(max(c0, 0), min(c1, NCOLS))


def row_lats(rows: slice) -> np.ndarray:
    y = Y0 - (np.arange(rows.start, rows.stop) + 0.5) * CELL_M
    return np.asarray(_to_geo.transform(np.zeros_like(y), y)[1])


def granule_time(name: str) -> datetime:
    m = re.search(r"_(\d{8}T\d{6})_", name)
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def urls(items: list[dict]) -> list[str]:
    """Protected HTTPS .h5 links of the daily granule, oldest first."""
    out = []
    for g in items:
        for u in g["umm"].get("RelatedUrls", []):
            url = u["URL"]
            if u.get("Type") == "GET DATA" and url.startswith("https://") and url.endswith(".h5") and f"{DAILY}_" in Path(url).name:
                out.append(url)
    return sorted(set(out), key=lambda u: granule_time(Path(u).name))


def subset(fileobj) -> dict[str, np.ndarray]:
    """Read the basin window from an open granule; checks the row mapping against the file's own latitudes."""
    import h5py

    rows, cols = window()
    with h5py.File(fileobj, "r") as h5:
        lat = h5["cell_lat"][rows, cols][:, 0]
        if not np.allclose(lat, row_lats(rows), atol=0.05):
            raise RuntimeError("EASE-Grid row mapping does not match the file's cell_lat")
        out = {}
        for v in VARS:
            a = h5[f"Geophysical_Data/{v}"][rows, cols].astype("float32")
            a[a < -9000] = np.nan  # fill value -9999
            out[v] = a
    return out


def series(paths: list[Path]) -> dict:
    """Basin-mean daily series (land cells only; the sea has no SMAP values)."""
    paths = sorted(paths, key=lambda p: granule_time(p.name))
    out: dict = {"t": [granule_time(p.name).isoformat() for p in paths], "source": f"NASA SMAP {SHORT} v{VERSION} (NSIDC), basin mean"}
    loaded = [np.load(p) for p in paths]
    for v, key in VARS.items():
        vals = []
        for d in loaded:
            a = d[v]
            vals.append(round(float(np.nanmean(a)), 4) if np.isfinite(a).any() else None)
        out[key] = vals
    return out
