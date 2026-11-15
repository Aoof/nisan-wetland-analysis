"""NASA OPERA DSWx (S1 radar, HLS optical): water classes per satellite pass.

Pipeline: CMR listing -> public BROWSE.png per MGRS tile (palette index == WTR class)
-> georeference from the tile ID -> warp to the shared Web Mercator AOI grid (nearest)
-> one GeoTIFF per pass. XYZ tiles, per-point history and per-place statistics all
read those GeoTIFFs. build_pass is the single place to swap in full 30 m granules later.
"""
import asyncio
import re
import warnings
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from .. import cmr, geo
from ..settings import DATA
from ..store import read_json, set_status, write_json
from . import dem

warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)  # browse PNGs are georeferenced by us

PRODUCTS = {
    "opera-dswx-s1": {"short": "OPERA_L3_DSWX-S1_V1", "days": 120, "window_h": 6, "label": "Surface water (radar)"},
    "opera-dswx-hls": {"short": "OPERA_L3_DSWX-HLS_V1", "days": 60, "window_h": 3, "label": "Surface water (optical)"},
}
# WTR codes: 0 dry, 1 open water, 2 partial surface water (HLS), 3 inundated vegetation (S1), 250-255 not observed
COLORMAP = {
    0: (0, 0, 0, 0), 1: (47, 109, 181, 235), 2: (122, 178, 226, 235), 3: (22, 160, 133, 235),
}
NODATA = 255
TILE_PX = 1024

_state_lock = threading.Lock()
_stacks: dict[str, dict] = {}
_versions: dict[str, int] = {}


def pass_dir(prod: str) -> Path:
    d = DATA / "passes" / prod
    d.mkdir(parents=True, exist_ok=True)
    return d


def index(prod: str) -> list[dict]:
    """Processed passes, oldest first."""
    return sorted(read_json(pass_dir(prod) / "index.json", []), key=lambda p: p["t"])


def pass_path(prod: str, pass_id: str) -> Path:
    return pass_dir(prod) / f"{pass_id}.tif"


def tile_id(ur: str) -> str | None:
    m = re.search(r"_T(\d{2}[A-Z]{3})_", ur)
    return m.group(1) if m else None


def acquisition_and_production(ur: str):
    m = re.search(r"_T\d{2}[A-Z]{3}_(\d{8}T\d{6})Z_(\d{8}T\d{6})Z_", ur)
    return (m.group(1), m.group(2)) if m else (None, None)


def group_passes(prod: str, granules: list[dict]) -> list[dict]:
    """One pass = granules of the same acquisition (several MGRS tiles); reprocessed duplicates collapse to the newest."""
    window = PRODUCTS[prod]["window_h"] * 3600
    best: dict[tuple[str, str], dict] = {}
    for g in granules:
        ur = g["umm"]["GranuleUR"]
        tile = tile_id(ur)
        acq, produced = acquisition_and_production(ur)
        if not tile or not acq or cmr.overlap_share(cmr.rect_of(g)) <= 0:
            continue
        key = (tile, acq)
        if key not in best or produced > best[key]["produced"]:
            best[key] = {"g": g, "tile": tile, "acq": acq, "produced": produced, "start": cmr.start_of(g)}
    items = sorted(best.values(), key=lambda x: x["start"])
    passes: list[dict] = []
    for it in items:
        if passes and (it["start"] - passes[-1]["start"]).total_seconds() <= window:
            passes[-1]["tiles"].append(it)
        else:
            passes.append({"start": it["start"], "tiles": [it]})
    for p in passes:
        p["id"] = f"{prod}-{p['start']:%Y%m%dT%H%M}"
    return passes


def browse_path(ur: str) -> Path:
    return DATA / "browse" / f"{ur}.png"


def fetch_browse(client: httpx.Client, g: dict) -> Path | None:
    ur = g["umm"]["GranuleUR"]
    p = browse_path(ur)
    if p.exists() and p.stat().st_size > 0:
        return p
    url = cmr.public_url(g, r"_BROWSE\.png$")
    if not url:
        return None
    r = client.get(url, follow_redirects=True)
    if r.status_code != 200:
        return None
    tmp = p.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(p)
    return p


def tile_to_grid(path: Path, tile: str) -> np.ndarray:
    """Warp one browse image (UTM, 1024 px over the 109.8 km tile) onto the AOI grid."""
    zone, x0, y0 = geo.mgrs_tile_origin(tile)
    px = geo.TILE_SIZE_M / TILE_PX
    with rasterio.open(path) as src:
        a = src.read(1)
        if a.shape != (TILE_PX, TILE_PX):
            raise ValueError(f"unexpected browse size {a.shape}")
    src_t = Affine(px, 0, x0, 0, -px, y0 + geo.TILE_SIZE_M)
    t, w, h = geo.aoi_grid()
    dst = np.full((h, w), NODATA, dtype="uint8")
    reproject(a, dst, src_transform=src_t, src_crs=geo.utm_crs(zone), src_nodata=NODATA,
              dst_transform=t, dst_crs="EPSG:3857", dst_nodata=NODATA, resampling=Resampling.nearest)
    return dst


def build_pass(prod: str, p: dict, client: httpx.Client) -> dict | None:
    t, w, h = geo.aoi_grid()
    out = np.full((h, w), NODATA, dtype="uint8")
    used = []
    for it in sorted(p["tiles"], key=lambda x: x["tile"]):
        path = fetch_browse(client, it["g"])
        if not path:
            continue
        grid = tile_to_grid(path, it["tile"])
        take = (out == NODATA) & (grid != NODATA)
        out[take] = grid[take]
        used.append(it["g"]["umm"]["GranuleUR"])
    if not used:
        return None
    # Codes above 3 are masks (HAND, layover/shadow, cloud, ocean, fill) = not observed.
    out[out > 3] = NODATA
    profile = {"driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": "uint8", "crs": "EPSG:3857",
               "transform": t, "nodata": NODATA, "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256}
    path = pass_path(prod, p["id"])
    tmp = path.with_suffix(".part")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(out, 1)
        dst.build_overviews([2, 4, 8], Resampling.nearest)
    tmp.replace(path)
    return {"id": p["id"], "t": p["start"].isoformat(), "granules": used, **stats(out)}


def stats(arr: np.ndarray) -> dict:
    """Inland statistics: the DEM sea mask keeps the Gulf out of every number."""
    land = dem.land_mask() if dem.available() else np.ones_like(arr, bool)
    area = geo.cell_area_km2()[:, None]
    seen = (arr != NODATA) & land
    land_km2 = float((area * land).sum()) or 1.0
    km2 = lambda m: round(float((area * (m & land)).sum()), 3)
    return {
        "observed_fraction": round(float((area * seen).sum()) / land_km2, 4),
        "water_km2": km2(np.isin(arr, (1, 2, 3))), "open_km2": km2(arr == 1),
        "partial_km2": km2(arr == 2), "veg_km2": km2(arr == 3),
    }


def process(prod: str, passes: list[dict], limit: int | None = None) -> int:
    """Build missing passes, newest first, so the latest map is available as soon as possible."""
    done = {p["id"] for p in index(prod)}
    todo = [p for p in reversed(passes) if p["id"] not in done and not pass_path(prod, p["id"]).exists()]
    if limit:
        todo = todo[:limit]
    # Prefetch browse images in parallel; everything after is CPU-bound.
    with httpx.Client(timeout=60, headers=cmr.UA) as client, ThreadPoolExecutor(6) as pool:
        for batch_start in range(0, len(todo), 6):
            batch = todo[batch_start:batch_start + 6]
            list(pool.map(lambda it: fetch_browse(client, it["g"]), [t for p in batch for t in p["tiles"]]))
            for p in batch:
                try:
                    row = build_pass(prod, p, client)
                except Exception as e:  # one bad pass must not stop the rest
                    print(f"[{prod}] {p['id']} failed: {e}")
                    continue
                if row:
                    with _state_lock:
                        rows = read_json(pass_dir(prod) / "index.json", [])
                        rows = [r for r in rows if r["id"] != row["id"]] + [row]
                        write_json(pass_dir(prod) / "index.json", rows)
                        _versions[prod] = _versions.get(prod, 0) + 1
    return len(todo)


async def refresh(prod: str) -> None:
    cfg = PRODUCTS[prod]
    set_status(prod, "refreshing", "Checking for new passes")
    try:
        granules = await cmr.search(cfg["short"], cfg["days"], max_age_s=0)
        passes = group_passes(prod, granules)
        _timeline_cache[prod] = passes
        n = await asyncio.to_thread(process, prod, passes)
        rows = index(prod)
        set_status(prod, "live" if rows else "unavailable", f"{len(rows)} passes processed, {len(passes)} found",
                   newest=rows[-1]["t"] if rows else None, found=len(passes), processed=len(rows), built=n)
    except Exception as e:
        set_status(prod, "error", f"{type(e).__name__}: {e}")


_timeline_cache: dict[str, list[dict]] = {}


def timeline(prod: str) -> list[dict]:
    """Every acquisition we know about (processed or not), for the time bar."""
    done = {p["id"] for p in index(prod)}
    if prod not in _timeline_cache:
        cached = read_json(DATA / "cmr" / f"{PRODUCTS[prod]['short']}.json")
        if not cached:
            return []
        _timeline_cache[prod] = group_passes(prod, cached["items"])
    return [{"id": p["id"], "t": p["start"].isoformat(), "tiles": sorted(t["tile"] for t in p["tiles"]), "processed": p["id"] in done}
            for p in _timeline_cache[prod]]


def stack(prod: str) -> dict:
    """All pass rasters in memory as (n, h, w) uint8 for point history and place statistics."""
    with _state_lock:
        v = _versions.get(prod, -1)
        cur = _stacks.get(prod)
        if cur and cur["v"] == v and cur["n"] == len(index(prod)):
            return cur
    rows = index(prod)
    t, w, h = geo.aoi_grid()
    arr = np.full((len(rows), h, w), NODATA, dtype="uint8")
    for i, r in enumerate(rows):
        with rasterio.open(pass_path(prod, r["id"])) as src:
            arr[i] = src.read(1)
    cur = {"v": _versions.get(prod, 0), "n": len(rows), "rows": rows, "arr": arr}
    with _state_lock:
        _stacks[prod] = cur
    return cur


def history(prod: str, lon: float, lat: float) -> list[dict]:
    cell = geo.xy_to_cell(lon, lat)
    s = stack(prod)
    if cell is None or not s["n"]:
        return []
    r, c = cell
    return [{"t": row["t"], "code": int(s["arr"][i, r, c])} for i, row in enumerate(s["rows"])]


def place_share(prod: str, lon: float, lat: float, radius_km: float) -> list[dict]:
    """Share of observed land cells within a radius that were wet, for every pass."""
    s = stack(prod)
    if not s["n"]:
        return []
    t, w, h = geo.aoi_grid()
    x, y = geo.to_mercator(lon, lat)
    r = radius_km * 1000 / np.cos(np.deg2rad(lat))
    cc, rr = np.meshgrid(np.arange(w), np.arange(h))
    inside = ((t.c + (cc + 0.5) * geo.RES - x) ** 2 + (t.f - (rr + 0.5) * geo.RES - y) ** 2 <= r * r)
    if dem.available():
        inside &= dem.land_mask()
    cells = s["arr"][:, inside]
    out = []
    for i, row in enumerate(s["rows"]):
        v = cells[i]
        seen = v != NODATA
        out.append({"t": row["t"], "seen": int(seen.sum()), "share": round(float(((v >= 1) & (v <= 3)).sum() / seen.sum()), 4) if seen.sum() >= 10 else None})
    return out
