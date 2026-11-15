"""SMAP and SWOT values, fetched by the API with the server-side Earthdata token.

Granule lists come from CMR (cached by cmr.search, shared with /api/timeline). Each granule's basin
subset is read over HTTPS and cached in DATA/cache/<source>/ as .npz, so a refresh only reads granules
it has not seen; a failed granule is retried on the next refresh. The series JSON is rebuilt from the
cache after every refresh, and cache files older than the window are pruned.
"""
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .. import cmr
from ..settings import DATA, EARTHDATA_TOKEN
from ..store import read_json, set_status, write_json
from . import smap, swot

SPECS = {
    # days: how far back the series reaches (the app's time bar spans 120 days back).
    "smap-l4": {"module": smap, "short": smap.SHORT, "days": 45, "series": "smap.json", "workers": 3},
    "swot-raster": {"module": swot, "short": swot.SHORT, "days": 120, "series": "swot.json", "workers": 3},
}
LOCK = {s: asyncio.Lock() for s in SPECS}


def series_path(source: str) -> Path:
    return DATA / "series" / SPECS[source]["series"]


def cache_dir(source: str) -> Path:
    return DATA / "cache" / source


async def granules(source: str) -> list[dict]:
    spec = SPECS[source]
    extra = {"readable_granule_name": "*_UTM15*", "options[readable_granule_name][pattern]": "true"} if source == "swot-raster" else None
    return await cmr.search(spec["short"], spec["days"], extra=extra, max_age_s=6 * 3600)


@lru_cache(maxsize=1)
def _login():
    """earthaccess session from EARTHDATA_TOKEN (bearer token; no username/password needed)."""
    import earthaccess

    auth = earthaccess.login(strategy="environment")
    if not auth or not auth.authenticated:
        raise RuntimeError("Earthdata login failed; check EARTHDATA_TOKEN")
    return earthaccess


def _fetch_one(source: str, url: str) -> str:
    """Read one granule's basin subset into the cache. Returns 'data', 'empty' or 'cached'."""
    import numpy as np

    mod = SPECS[source]["module"]
    stem = Path(url).stem
    npz, empty = cache_dir(source) / f"{stem}.npz", cache_dir(source) / f"{stem}.empty"
    if npz.exists() or empty.exists():
        return "cached"
    ea = _login()
    [f] = ea.open([url], show_progress=False)
    try:
        arrays = mod.subset(f)
    finally:
        f.close()
    if arrays is None:
        empty.touch()  # tile touches the box but holds no water data inside it
        return "empty"
    part = npz.with_suffix(".part.npz")
    np.savez_compressed(part, **arrays)
    part.replace(npz)
    return "data"


def _sync(source: str, urls: list[str]) -> tuple[int, list[str]]:
    cache_dir(source).mkdir(parents=True, exist_ok=True)
    new, failed = 0, []
    with ThreadPoolExecutor(SPECS[source]["workers"]) as pool:
        futs = {pool.submit(_fetch_one, source, u): u for u in urls}
        for fut in as_completed(futs):
            try:
                new += fut.result() == "data"
            except Exception as e:  # keep going; retried next refresh
                failed.append(f"{Path(futs[fut]).name}: {type(e).__name__}: {e}"[:200])
    return new, failed


def _rebuild(source: str, urls: list[str]) -> dict | None:
    """Series from the cached subsets of the granules still in the window; prune the rest."""
    keep = {Path(u).stem for u in urls}
    cutoff = datetime.now(timezone.utc) - timedelta(days=SPECS[source]["days"] + 5)
    paths = []
    for p in cache_dir(source).glob("*"):
        stem = re.sub(r"\.(npz|empty)$", "", p.name)
        if p.suffix == ".npz" and stem in keep:
            paths.append(p)
        elif stem not in keep and datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) < cutoff:
            p.unlink(missing_ok=True)
    if not paths:
        return None
    out = SPECS[source]["module"].series(paths)
    write_json(series_path(source), out)
    return out


async def refresh(source: str) -> None:
    if LOCK[source].locked():
        return
    async with LOCK[source]:
        old = series(source)
        if not EARTHDATA_TOKEN:
            set_status(source, "live" if old else "unavailable",
                       "EARTHDATA_TOKEN is not set" + ("; showing earlier values" if old else ""), newest=(old or {}).get("t", [None])[-1] if old else None)
            return
        set_status(source, "refreshing", "Reading new granules from Earthdata")
        try:
            items = await granules(source)
            urls = SPECS[source]["module"].urls(items)
            new, failed = await asyncio.to_thread(_sync, source, urls)
            s = await asyncio.to_thread(_rebuild, source, urls)
        except Exception as e:
            set_status(source, "error" if not old else "live", f"{type(e).__name__}: {e}"[:300] + ("; showing earlier values" if old else ""))
            return
        if not s or not s["t"]:
            set_status(source, "awaiting-data", f"{len(urls)} granules found, none with values over the basin yet"
                       + (f"; {len(failed)} failed: {failed[0]}" if failed else ""), found=len(urls))
            return
        msg = f"{len(s['t'])} observations ({new} new)" + (f"; {len(failed)} granules failed and will be retried: {failed[0]}" if failed else "")
        set_status(source, "live", msg, newest=s["t"][-1], found=len(urls), processed=len(urls) - len(failed))


def series(source: str) -> dict | None:
    return read_json(series_path(source))


async def timeline(source: str) -> list[dict]:
    """Acquisition ticks from CMR (SMAP: one per day; SWOT: UTM-15 passes)."""
    items = await granules(source)
    out, seen = [], set()
    for g in items:
        t = cmr.start_of(g)
        key = f"{t:%Y%m%d}" if source == "smap-l4" else f"{t:%Y%m%d%H}{t.minute // 20}"
        if key in seen or (source == "swot-raster" and not re.search(r"_UTM15", g["umm"]["GranuleUR"])):
            continue
        seen.add(key)
        out.append({"id": g["umm"]["GranuleUR"], "t": t.isoformat(), "tiles": [], "processed": True})
    return out
