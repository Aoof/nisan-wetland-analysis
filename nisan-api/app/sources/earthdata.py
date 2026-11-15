"""SMAP and SWOT values: run the existing sandbox scripts with the server-side Earthdata token,
then publish their CSV output as compact series. The token never leaves this process.
"""
import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .. import cmr
from ..settings import DATA, EARTHDATA_TOKEN, SANDBOXES
from ..store import read_json, set_status, write_json

SPECS = {
    "smap-l4": {"dir": "smap-sandbox", "script": "fetch_smap.py", "args": ["l4"], "days": 21, "csv": "coatzacoalcos_l4_*.csv", "series": "smap.json",
                "short": "SPL4SMGP", "version": "008"},
    "swot-raster": {"dir": "swot-sandbox", "script": "fetch_swot.py", "args": [], "days": 60, "csv": "coatzacoalcos_swot_*.csv", "series": "swot.json",
                    "short": "SWOT_L2_HR_Raster_100m_D"},
}


def series_path(source: str) -> Path:
    return DATA / "series" / SPECS[source]["series"]


async def run_sandbox(source: str) -> tuple[bool, str]:
    spec = SPECS[source]
    folder = SANDBOXES / spec["dir"]
    py = folder / ".venv" / "bin" / "python"
    if not EARTHDATA_TOKEN:
        return False, "EARTHDATA_TOKEN is not set in nisan-app/.env"
    if not py.exists():
        return False, f"{spec['dir']} has no .venv; run its setup first"
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=spec["days"])
    cmd = [str(py), spec["script"], *spec["args"], "--start", start.isoformat(), "--end", end.isoformat(), "--workers", "2"]
    env = {**os.environ, "EARTHDATA_TOKEN": EARTHDATA_TOKEN}
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=folder, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=3600)
    except asyncio.TimeoutError:
        proc.kill()
        return False, "sandbox run timed out"
    tail = out.decode(errors="replace").strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)[-300:]


def publish(source: str) -> bool:
    """Newest sandbox CSV -> series JSON."""
    spec = SPECS[source]
    files = sorted((SANDBOXES / spec["dir"] / "data" / "processed").glob(spec["csv"]), key=lambda p: p.stat().st_mtime)
    if not files:
        return False
    df = pd.read_csv(files[-1])
    tcol = df.columns[0]
    df[tcol] = pd.to_datetime(df[tcol], utc=True)
    df = df.sort_values(tcol)
    if source == "smap-l4":
        cols = {"rootzone_wetness": "sm_rootzone_wetness_mean", "surface_wetness": "sm_surface_wetness_mean",
                "rootzone_m3m3": "sm_rootzone_mean", "surface_m3m3": "sm_surface_mean"}
    else:
        cols = {"wse_median_m": "wse_median_m", "wse_p10_m": "wse_p10_m", "wse_p90_m": "wse_p90_m", "water_area_km2": "water_area_km2"}
    out = {"t": [t.isoformat() for t in df[tcol]], "source_file": files[-1].name}
    for k, c in cols.items():
        if c in df:
            out[k] = [None if pd.isna(v) else round(float(v), 4) for v in df[c]]
    write_json(series_path(source), out)
    return True


async def refresh(source: str) -> None:
    set_status(source, "refreshing", "Fetching values from Earthdata (can take several minutes)")
    ok, msg = await run_sandbox(source)
    if publish(source):
        s = read_json(series_path(source), {})
        set_status(source, "live", f"{len(s.get('t', []))} observations" + ("" if ok else " (last refresh failed; showing earlier values)"), newest=s["t"][-1])
    else:
        set_status(source, "awaiting-data", msg or "No values yet")


def series(source: str) -> dict | None:
    return read_json(series_path(source))


async def timeline(source: str) -> list[dict]:
    """Acquisition ticks from CMR (SMAP: one per day; SWOT: UTM-15 passes)."""
    spec = SPECS[source]
    extra = {"readable_granule_name": "*_UTM15*", "options[readable_granule_name][pattern]": "true"} if source == "swot-raster" else None
    items = await cmr.search(spec["short"], 120 if source == "swot-raster" else 45, extra=extra, max_age_s=6 * 3600)
    out, seen = [], set()
    for g in items:
        t = cmr.start_of(g)
        key = f"{t:%Y%m%d}" if source == "smap-l4" else f"{t:%Y%m%d%H}{t.minute // 20}"
        if key in seen or (source == "swot-raster" and not re.search(r"_UTM15", g["umm"]["GranuleUR"])):
            continue
        seen.add(key)
        out.append({"id": g["umm"]["GranuleUR"], "t": t.isoformat(), "tiles": [], "processed": True})
    return out
