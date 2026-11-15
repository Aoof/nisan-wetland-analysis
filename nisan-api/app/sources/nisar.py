"""NISAR L2 GCOV browse images (public, no login): a backscatter composite, not a water map.

The browse PNG is a regular lat/lon grid whose corners are in the sibling KML
(gx:LatLonQuad). We write it as an EPSG:4326 GeoTIFF; rio-tiler warps it to Web
Mercator per tile, so there is no corner interpolation. Water classes from the full
GCOV product are not produced yet.
"""
import asyncio
import re
import warnings
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_bounds

from .. import cmr
from ..settings import BBOX, DATA
from ..store import read_json, set_status, write_json

warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)
SOURCE = "nisar-gcov"
COLLECTIONS = ["NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1"]
KEEP = 8
MIN_COVERAGE = 0.25  # share of the basin a pass must cover to be shown


def path_for(granule_id: str) -> Path:
    return DATA / "nisar" / f"{granule_id}.tif"


def stamp(ur: str) -> str:
    m = re.search(r"_(\d{8}T\d{6})_\d{8}T\d{6}_", ur)
    return m.group(1) if m else ur


def coverage(ring: list[list[float]], n: int = 24) -> float:
    """Share of the AOI inside a footprint polygon (even-odd rule on an n x n sample grid)."""
    w, so, e, no = BBOX
    xs, ys = np.meshgrid(np.linspace(w, e, n), np.linspace(so, no, n))
    px, py = xs.ravel(), ys.ravel()
    inside = np.zeros(px.shape, bool)
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if y1 == y2:
            continue
        crosses = ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1)
        inside ^= crosses
    return float(inside.mean())


async def listing() -> list[dict]:
    """Granules over the AOI, V1 preferred over provisional for the same acquisition."""
    got = []
    for short in COLLECTIONS:
        for g in await cmr.search(short, None, start="2025-10-01T00:00:00Z", max_age_s=0):
            got.append((short, g))
    best: dict[str, tuple[str, dict]] = {}
    for short, g in got:
        k = stamp(g["umm"]["GranuleUR"])
        if k not in best or ("PROVISIONAL" in best[k][0] and "PROVISIONAL" not in short):
            best[k] = (short, g)
    out = []
    for short, g in sorted(best.values(), key=lambda x: cmr.start_of(x[1])):
        a = cmr.attrs(g)
        out.append({
            "id": g["umm"]["GranuleUR"], "t": cmr.start_of(g).isoformat(), "version": "provisional" if "PROVISIONAL" in short else "v1",
            "track": a.get("TRACK_NUMBER"), "frame": a.get("FRAME_NUMBER"), "direction": a.get("ASCENDING_DIRECTION") or a.get("ASCENDING_DESCENDING"),
            "footprint": cmr.footprint_of(g), "coverage": round(coverage(cmr.footprint_of(g)), 3), "png": cmr.public_url(g, r"_LATLON\.png$"), "kml": cmr.public_url(g, r"_LATLON\.kml$"),
        })
    return out


def build(client: httpx.Client, item: dict) -> bool:
    out = path_for(item["id"])
    if out.exists() or not item["png"] or not item["kml"]:
        return out.exists()
    kml = client.get(item["kml"], follow_redirects=True).text
    quad = re.search(r"LatLonQuad>\s*<coordinates>([^<]+)</coordinates>", kml)
    if not quad:
        return False
    # lower-left, lower-right, upper-right, upper-left (lon,lat)
    ll, lr, ur, ul = [tuple(map(float, p.split(","))) for p in quad.group(1).split()]
    if abs(ll[1] - lr[1]) > 1e-6 or abs(ll[0] - ul[0]) > 1e-6:
        return False  # not axis-aligned: would need a warp; none seen so far
    png = client.get(item["png"], follow_redirects=True)
    if png.status_code != 200:
        return False
    tmp = out.with_suffix(".png.part")
    tmp.write_bytes(png.content)
    with rasterio.open(tmp) as src:
        rgb = src.read()
    h, w = rgb.shape[1:]
    alpha = ((rgb.max(axis=0) > 0) * 255).astype("uint8")
    profile = {"driver": "GTiff", "width": w, "height": h, "count": 4, "dtype": "uint8", "crs": "EPSG:4326",
               "transform": from_bounds(ll[0], ll[1], ur[0], ur[1], w, h), "compress": "deflate", "tiled": True,
               "blockxsize": 256, "blockysize": 256, "photometric": "RGB", "alpha": "YES"}
    part = out.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(np.concatenate([rgb[:3], alpha[None]]))
    tmp.unlink(missing_ok=True)
    part.replace(out)
    return True


async def refresh() -> None:
    set_status(SOURCE, "refreshing", "Checking for new passes")
    try:
        items = await listing()
        write_json(DATA / "series" / "nisar_listing.json", items)
        with httpx.Client(timeout=120, headers=cmr.UA) as client:
            # Only passes that actually cover the basin are worth an image.
            useful = [i for i in items if i["coverage"] >= MIN_COVERAGE]
            for it in reversed(useful[-KEEP:]):
                await asyncio.to_thread(build, client, it)
        done = sum(path_for(i["id"]).exists() for i in items)
        set_status(SOURCE, "awaiting-data" if not done else "live",
                   f"{len(items)} acquisitions ({len(useful)} cover the basin); backscatter image for the latest {min(KEEP, len(useful))}. Water classes are not produced yet.",
                   newest=items[-1]["t"] if items else None, found=len(items), processed=done)
    except Exception as e:
        set_status(SOURCE, "error", f"{type(e).__name__}: {e}")


def timeline() -> list[dict]:
    items = read_json(DATA / "series" / "nisar_listing.json", [])
    return [{"id": i["id"], "t": i["t"], "tiles": [], "processed": path_for(i["id"]).exists() and i.get("coverage", 1) >= MIN_COVERAGE, "coverage": i.get("coverage"), "version": i["version"], "track": i["track"], "frame": i["frame"]} for i in items]


def footprints(limit: int = 1) -> list[dict]:
    items = read_json(DATA / "series" / "nisar_listing.json", [])
    return [{"id": i["id"], "t": i["t"], "ring": i["footprint"]} for i in items[-limit:]]
