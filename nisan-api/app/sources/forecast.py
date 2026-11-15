"""GloFAS river discharge and ECMWF rain + soil moisture, via Open-Meteo (no key).

Output is one compact JSON the browser reads in a single request. The 20-year
GloFAS climatology (day-of-year median / 90th percentile) is computed here once
and cached, so the client never downloads the raw history.
"""
import json
from datetime import datetime, timezone

import httpx
import numpy as np

from .. import cmr
from ..settings import DATA, FLOOD_API, PLACES_JSON, WEATHER_API
from ..store import read_json, set_status, write_json

OUT = DATA / "forecast" / "forecast.json"
CLIM = DATA / "forecast" / "climatology.json"
SM_LAYERS = [("soil_moisture_0_to_1cm", 1), ("soil_moisture_1_to_3cm", 2), ("soil_moisture_3_to_9cm", 6),
             ("soil_moisture_9_to_27cm", 18), ("soil_moisture_27_to_81cm", 54)]
POROSITY = 0.47  # assumed clay-loam floodplain; turns m3/m3 into a share of saturation


def places():
    return json.loads(PLACES_JSON.read_text())


def _doy(d: datetime) -> int:
    return d.timetuple().tm_yday


async def climatology(client: httpx.AsyncClient, gauges: list[dict]) -> dict:
    """{gauge_id: {doy: [p50, p90]}} from GloFAS 2006..last year, +-7-day window."""
    cached = read_json(CLIM)
    if cached and cached.get("ids") == [g["id"] for g in gauges]:
        return cached["data"]
    r = await client.get(FLOOD_API, params={
        "latitude": ",".join(str(g["at"][1]) for g in gauges), "longitude": ",".join(str(g["at"][0]) for g in gauges),
        "daily": "river_discharge", "start_date": "2006-01-01", "end_date": f"{datetime.now(timezone.utc).year - 1}-12-31",
    })
    r.raise_for_status()
    data = {}
    for g, resp in zip(gauges, r.json()):
        days = [datetime.fromisoformat(s) for s in resp["daily"]["time"]]
        q = np.array([np.nan if v is None else v for v in resp["daily"]["river_discharge"]], dtype="float64")
        doy = np.array([_doy(d) for d in days])
        table: dict[str, list] = {}
        for k in range(1, 367):
            sel = np.abs(((doy - k + 183) % 366) - 183) <= 7
            vals = q[sel][~np.isnan(q[sel])]
            table[str(k)] = [round(float(np.percentile(vals, 50)), 1), round(float(np.percentile(vals, 90)), 1)] if len(vals) else [None, None]
        data[g["id"]] = table
    write_json(CLIM, {"ids": [g["id"] for g in gauges], "data": data})
    return data


async def refresh() -> None:
    set_status("forecast", "refreshing", "Fetching river and rain forecast")
    cfg = places()
    gauges, pl = cfg["gauges"], cfg["places"]
    try:
        async with httpx.AsyncClient(timeout=60, headers=cmr.UA) as c:
            clim = await climatology(c, gauges)
            rf = await c.get(FLOOD_API, params={
                "latitude": ",".join(str(g["at"][1]) for g in gauges), "longitude": ",".join(str(g["at"][0]) for g in gauges),
                "daily": "river_discharge,river_discharge_max", "past_days": 92, "forecast_days": 30,
            })
            rf.raise_for_status()
            sm = ",".join(n for n, _ in SM_LAYERS)
            rw = await c.get(WEATHER_API, params={
                "latitude": ",".join(str(p["at"][1]) for p in pl), "longitude": ",".join(str(p["at"][0]) for p in pl),
                "hourly": f"precipitation,{sm}", "daily": "precipitation_sum,precipitation_probability_max",
                "past_days": 31, "forecast_days": 10, "timezone": "UTC",
            })
            rw.raise_for_status()
        out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "porosity": POROSITY, "gauges": [], "places": []}
        for g, resp in zip(gauges, rf.json()):
            days = resp["daily"]["time"]
            c50, c90 = [], []
            for s in days:
                k = _doy(datetime.fromisoformat(s))
                a = clim[g["id"]].get(str(k), [None, None])
                c50.append(a[0]); c90.append(a[1])
            out["gauges"].append({
                **g, "cell": [resp["longitude"], resp["latitude"]], "days": days,
                "q": [None if v is None else round(v, 1) for v in resp["daily"]["river_discharge"]],
                "qMax": [None if v is None else round(v, 1) for v in resp["daily"].get("river_discharge_max", [])],
                "clim50": c50, "clim90": c90,
            })
        for p, resp in zip(pl, rw.json()):
            h = resp["hourly"]
            wet = []
            for i in range(len(h["time"])):
                tot = dep = 0.0
                for name, d in SM_LAYERS:
                    v = h[name][i]
                    if v is not None:
                        tot += v * d; dep += d
                wet.append(round(min(1.0, tot / dep / POROSITY), 3) if dep else None)
            out["places"].append({
                "id": p["id"], "hours": h["time"], "rain": [None if v is None else round(v, 1) for v in h["precipitation"]],
                "wetness": wet, "days": resp["daily"]["time"], "rainDaily": resp["daily"]["precipitation_sum"],
                "rainProb": resp["daily"].get("precipitation_probability_max", []),
            })
        write_json(OUT, out)
        set_status("forecast", "live", f"{len(out['gauges'])} river cells, {len(out['places'])} places", newest=out["updated"])
    except Exception as e:
        set_status("forecast", "error" if not OUT.exists() else "live", f"Refresh failed ({type(e).__name__}); showing the last good copy")


def current() -> dict | None:
    return read_json(OUT)
