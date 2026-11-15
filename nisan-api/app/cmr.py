"""NASA CMR granule search (UMM-G JSON). Public; tells us what exists and where its files are."""
import re
from datetime import datetime, timedelta, timezone

import httpx

from .settings import BBOX, CMR, DATA
from .store import read_json, write_json

UA = {"User-Agent": "nisan-api/0.1 (+flood watch)"}


async def search(short_name: str, days: int | None, start: str | None = None, extra: dict | None = None, max_age_s: int = 3 * 3600) -> list[dict]:
    """All granules over the AOI for a collection; cached on disk, refreshed when older than max_age_s."""
    cache = DATA / "cmr" / f"{short_name}.json"
    cached = read_json(cache)
    if cached and datetime.now(timezone.utc).timestamp() - cached["fetched"] < max_age_s:
        return cached["items"]
    t1 = datetime.now(timezone.utc)
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else t1 - timedelta(days=days or 120)
    params = {
        "short_name": short_name, "bounding_box": ",".join(map(str, BBOX)), "page_size": 2000,
        "temporal": f"{t0:%Y-%m-%dT%H:%M:%SZ},{t1:%Y-%m-%dT%H:%M:%SZ}", "sort_key": "start_date", **(extra or {}),
    }
    async with httpx.AsyncClient(timeout=60, headers=UA) as c:
        r = await c.get(CMR, params=params)
        r.raise_for_status()
        items = r.json()["items"]
    write_json(cache, {"fetched": t1.timestamp(), "items": items})
    return items


def start_of(g: dict) -> datetime:
    t = g["umm"]["TemporalExtent"]
    s = (t.get("RangeDateTime") or {}).get("BeginningDateTime") or t.get("SingleDateTime")
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def end_of(g: dict) -> datetime:
    t = g["umm"]["TemporalExtent"]
    s = (t.get("RangeDateTime") or {}).get("EndingDateTime") or (t.get("RangeDateTime") or {}).get("BeginningDateTime") or t.get("SingleDateTime")
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def rect_of(g: dict):
    """(W, S, E, N) from a granule's polygon or bounding rectangle."""
    geo = g["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]
    if geo.get("GPolygons"):
        pts = geo["GPolygons"][0]["Boundary"]["Points"]
        xs, ys = [p["Longitude"] for p in pts], [p["Latitude"] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    r = geo["BoundingRectangles"][0]
    return r["WestBoundingCoordinate"], r["SouthBoundingCoordinate"], r["EastBoundingCoordinate"], r["NorthBoundingCoordinate"]


def footprint_of(g: dict):
    geo = g["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]
    if geo.get("GPolygons"):
        return [[p["Longitude"], p["Latitude"]] for p in geo["GPolygons"][0]["Boundary"]["Points"]]
    w, s, e, n = rect_of(g)
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def attrs(g: dict) -> dict:
    return {a["Name"]: (a.get("Values") or [""])[0] for a in g["umm"].get("AdditionalAttributes", [])}


def public_url(g: dict, pattern: str) -> str | None:
    """First public https related URL matching a regex (browse images etc.)."""
    for u in g["umm"].get("RelatedUrls", []):
        if u["URL"].startswith("https://") and "protected" not in u["URL"] and re.search(pattern, u["URL"]):
            return u["URL"]
    return None


def overlap_share(rect, bbox=BBOX) -> float:
    w, s, e, n = rect
    ww, ee, ss, nn = max(w, bbox[0]), min(e, bbox[2]), max(s, bbox[1]), min(n, bbox[3])
    if ee <= ww or nn <= ss:
        return 0.0
    return (ee - ww) * (nn - ss) / ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
