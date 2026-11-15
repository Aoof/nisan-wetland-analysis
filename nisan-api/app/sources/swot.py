"""SWOT L2 HR Raster 100 m (PO.DAAC) for the basin: water surface elevation and water area per pass.

Each raster tile is opened over HTTPS, cut to the basin and snapped onto the shared UTM 15N 100 m grid;
the cut is cached per tile as .npz (or an .empty marker when the tile has no water inside the basin).
Adjacent scenes of one pass are merged into one time step.
"""
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .. import geo

SHORT = "SWOT_L2_HR_Raster_100m_D"
ZONE_TAG = "_UTM15"  # the basin is in UTM zone 15; skip tiles projected in other zones
RES = 100.0
VARS = ["wse", "wse_uncert", "wse_qual", "water_frac", "water_area"]
MAX_WSE_QUAL = 1  # 0 good, 1 suspect, 2 degraded, 3 bad
MIN_WATER_FRAC = 0.5
NAME_RE = re.compile(r"_(?P<cycle>\d{3})_(?P<pass>\d{3})_(?P<scene>\d{3}[FR])_(?P<start>\d{8}T\d{6})_")


def parse(name: str) -> dict:
    m = NAME_RE.search(name)
    if not m:
        raise ValueError(f"unexpected SWOT raster name {name}")
    return m.groupdict()


def granule_time(name: str) -> datetime:
    return datetime.strptime(parse(name)["start"], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def urls(items: list[dict]) -> list[str]:
    out = []
    for g in items:
        for u in g["umm"].get("RelatedUrls", []):
            url = u["URL"]
            if u.get("Type") == "GET DATA" and url.startswith("https://") and url.endswith(".nc") and ZONE_TAG in Path(url).name:
                out.append(url)
    return sorted(set(out), key=lambda u: granule_time(Path(u).name))


def grid_coords() -> tuple[np.ndarray, np.ndarray]:
    t, w, h = geo.utm_grid(RES)
    return t.c + RES / 2 + RES * np.arange(w), t.f - RES / 2 - RES * np.arange(h)


def subset(fileobj) -> dict[str, np.ndarray] | None:
    """The basin cut of one tile on the shared grid, or None when there is no water data inside it."""
    import xarray as xr

    x, y = grid_coords()
    with xr.open_dataset(fileobj, engine="h5netcdf", mask_and_scale=True) as ds:
        sub = ds[VARS].sel(x=slice(x.min() - RES, x.max() + RES))
        ysl = slice(y.max() + RES, y.min() - RES) if sub.y[0] > sub.y[-1] else slice(y.min() - RES, y.max() + RES)
        sub = sub.sel(y=ysl)
        if sub.sizes["x"] == 0 or sub.sizes["y"] == 0:
            return None
        sub = sub.reindex(x=x, y=y, method="nearest", tolerance=RES / 2)
        out = {v: sub[v].values.astype("float32") for v in VARS}
    return out if np.isfinite(out["wse"]).any() else None


def series(paths: list[Path]) -> dict:
    """Per pass: median and 10-90 % range of water surface elevation over good water pixels, and water area."""
    passes: dict[tuple[str, str], tuple[dict, dict]] = {}
    for p in sorted(paths, key=lambda p: parse(p.name)["start"]):
        m, d = parse(p.name), dict(np.load(p))
        key = (m["cycle"], m["pass"])
        if key not in passes:
            passes[key] = (m, d)
            continue
        merged = passes[key][1]
        fill = ~np.isfinite(merged["wse"]) & np.isfinite(d["wse"])
        for v in VARS:
            merged[v][fill] = d[v][fill]
    out: dict = {"t": [], "source": f"NASA/CNES SWOT {SHORT} (PO.DAAC), basin", "cycle": [], "pass": [],
                 "wse_median_m": [], "wse_p10_m": [], "wse_p90_m": [], "water_area_km2": [], "good_water_pixels": []}
    r = lambda v: None if v is None or not np.isfinite(v) else round(float(v), 4)  # noqa: E731
    for m, d in passes.values():
        ok_q = np.nan_to_num(d["wse_qual"], nan=9) <= MAX_WSE_QUAL
        good = ok_q & (np.nan_to_num(d["water_frac"]) >= MIN_WATER_FRAC) & np.isfinite(d["wse"])
        wse = d["wse"][good]
        out["t"].append(datetime.strptime(m["start"], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat())
        out["cycle"].append(int(m["cycle"]))
        out["pass"].append(int(m["pass"]))
        out["wse_median_m"].append(r(np.median(wse)) if wse.size else None)
        out["wse_p10_m"].append(r(np.quantile(wse, 0.1)) if wse.size else None)
        out["wse_p90_m"].append(r(np.quantile(wse, 0.9)) if wse.size else None)
        out["water_area_km2"].append(r(np.nansum(np.where(ok_q, d["water_area"], np.nan)) / 1e6))
        out["good_water_pixels"].append(int(good.sum()))
    return out
