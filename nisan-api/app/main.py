"""NISAN data API. Every endpoint answers from local copies; background jobs keep them fresh."""
import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import jobs, tiles
from .settings import BBOX, DATA
from .sources import dem, earthdata, forecast, nisar, opera
from .store import get_status, load_status, now_iso
from .web import web_files

PRODS = list(opera.PRODUCTS)
_bg: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_status()
    jobs.start()
    _bg.append(asyncio.create_task(jobs.startup()))
    yield
    for t in _bg:
        t.cancel()
    jobs.scheduler.shutdown(wait=False)


app = FastAPI(title="NISAN data API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


def cached(request: Request, body: object, max_age: int = 60, swr: int = 600) -> Response:
    """JSON with an ETag so revalidation costs one tiny 304."""
    raw = json.dumps(body, separators=(",", ":")).encode()
    etag = '"' + hashlib.md5(raw).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate={swr}"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(raw, media_type="application/json", headers=headers)


def tile_url(layer: str, pass_id: str) -> str:
    return f"/api/tiles/{layer}/{pass_id}/{{z}}/{{x}}/{{y}}.png"


@app.get("/api/health")
def health():
    return {"ok": True, "time": now_iso(), "bbox": BBOX, "earthdata": bool(earthdata.EARTHDATA_TOKEN)}


@app.get("/api/now")
def now(request: Request):
    """Everything the first screen needs, in one small response."""
    water = {}
    for prod in PRODS:
        rows = opera.index(prod)
        if rows:
            last = rows[-1]
            water[prod] = {**last, "tiles": tile_url(prod, last["id"]), "count": len(rows)}
    n = nisar.timeline()
    built = [i for i in n if i["processed"]]
    return cached(request, {
        "generated": now_iso(), "sources": get_status(), "water": water,
        "hand": {"tiles": f"/api/tiles/hand/{{z}}/{{x}}/{{y}}.png?v={dem.version()}"} if dem.available() else None,
        "nisar": {**built[-1], "tiles": tile_url("nisar-gcov", built[-1]["id"])} if built else None,
        "forecastUpdated": (forecast.current() or {}).get("updated"),
    }, max_age=15, swr=60)


@app.get("/api/forecast")
def get_forecast(request: Request):
    f = forecast.current()
    if not f:
        raise HTTPException(503, "forecast not ready yet")
    return cached(request, f, max_age=60, swr=300)


@app.get("/api/places")
def places(request: Request):
    """Per-place terrain exposure and local surface-water history (drives zone risk)."""
    cfg = forecast.places()
    out = []
    versions = {p: len(opera.index(p)) for p in PRODS}
    for p in cfg["places"]:
        lon, lat = p["at"]
        shares = dem.class_shares(lon, lat, p["radiusKm"]) if dem.available() else {}
        out.append({
            "id": p["id"], "shares": shares,
            "water": {prod: opera.place_share(prod, lon, lat, p["radiusKm"]) for prod in PRODS if versions[prod]},
        })
    return cached(request, {"places": out, "passes": versions}, max_age=60, swr=600)


@app.get("/api/timeline/{source}")
async def timeline(source: str, request: Request):
    if source in opera.PRODUCTS:
        data = opera.timeline(source)
    elif source == "nisar-gcov":
        data = nisar.timeline()
    elif source in earthdata.SPECS:
        data = await earthdata.timeline(source)
    else:
        raise HTTPException(404, "unknown source")
    return cached(request, data, max_age=300, swr=3600)


@app.get("/api/passes/{prod}")
def passes(prod: str, request: Request):
    """Processed passes with inland water statistics (the basin-wide series)."""
    if prod not in opera.PRODUCTS:
        raise HTTPException(404, "unknown product")
    return cached(request, [{k: v for k, v in r.items() if k != "granules"} for r in opera.index(prod)], max_age=60, swr=600)


@app.get("/api/series/{source}")
def series(source: str, request: Request):
    if source not in earthdata.SPECS:
        raise HTTPException(404, "unknown source")
    s = earthdata.series(source)
    if not s:  # first fill still running: an empty series, re-asked for soon
        return cached(request, {"t": [], "pending": True, "status": get_status().get(source, {}).get("message", "")}, max_age=60, swr=0)
    return cached(request, s, max_age=300, swr=3600)


@app.get("/api/point")
async def point(request: Request, lon: float = Query(...), lat: float = Query(...)):
    if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
        raise HTTPException(422, "outside the basin")
    terrain = await asyncio.to_thread(dem.point, lon, lat)
    water = {p: await asyncio.to_thread(opera.history, p, lon, lat) for p in PRODS}
    return cached(request, {"terrain": terrain, "water": water}, max_age=60, swr=600)


# 255 = not observed; 0 = dry. Display palette lives with the tiles, not the browser.
@app.get("/api/tiles/hand/{z}/{x}/{y}.png")
def hand_tile(z: int, x: int, y: int):
    if not dem.available():
        raise HTTPException(404)
    return tiles.png_tile(dem.HAND_CLASS, z, x, y, colormap=dem.COLORMAP)  # URL carries ?v=, so it can be immutable


@app.get("/api/tiles/nisar-gcov/{granule}/{z}/{x}/{y}.png")
def nisar_tile(granule: str, z: int, x: int, y: int):
    p = nisar.path_for(granule)
    if not p.exists():
        raise HTTPException(404)
    return tiles.png_tile(p, z, x, y, indexes=(1, 2, 3))


@app.get("/api/tiles/{layer}/{pass_id}/{z}/{x}/{y}.png")
def water_tile(layer: str, pass_id: str, z: int, x: int, y: int):
    if layer not in opera.PRODUCTS:
        raise HTTPException(404)
    p = opera.pass_path(layer, pass_id)
    if not p.exists():
        raise HTTPException(404)
    return tiles.png_tile(p, z, x, y, colormap=opera.COLORMAP)


# Single-container deployments: the webroot (ACME challenges, robots.txt, ...) and the built web app at /,
# so the browser calls /api on the same origin. Mounted last so every /api route above wins.
_web = web_files(os.environ.get("NISAN_WEBROOT"), os.environ.get("NISAN_STATIC"))
if _web:
    app.mount("/", _web, name="web")
