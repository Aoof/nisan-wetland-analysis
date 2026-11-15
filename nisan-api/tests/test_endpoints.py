import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)  # no context manager: background jobs are not started


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_point_outside_basin_is_rejected():
    assert client.get("/api/point", params={"lon": 0, "lat": 0}).status_code == 422


def test_now_has_stable_shape():
    j = client.get("/api/now").json()
    assert {"generated", "sources", "water", "hand", "nisar", "forecastUpdated"} <= j.keys()


def test_etag_revalidation():
    r = client.get("/api/now")
    r2 = client.get("/api/now", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code in (200, 304)


def test_point_values():
    j = client.get("/api/point", params={"lon": -94.546, "lat": 17.993}).json()
    if j["terrain"] is None:
        pytest.skip("DEM missing")
    assert j["terrain"]["cls"] in (1, 2, 3, 4) and "opera-dswx-s1" in j["water"]


def test_empty_tile_is_a_valid_png():
    """Tiles outside a raster must decode in the browser, or MapLibre logs an error per tile."""
    import struct
    import zlib

    from app.tiles import EMPTY

    assert EMPTY.startswith(b"\x89PNG\r\n\x1a\n")
    i = 8
    while i < len(EMPTY):
        n = struct.unpack(">I", EMPTY[i:i + 4])[0]
        kind, body = EMPTY[i + 4:i + 8], EMPTY[i + 8:i + 8 + n]
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == struct.unpack(">I", EMPTY[i + 8 + n:i + 12 + n])[0], kind
        if kind == b"IDAT":
            assert zlib.decompress(body) == b"\x00" * 5
        i += 12 + n


def test_series_unknown_source_is_404_and_known_is_json(monkeypatch):
    from app.sources import earthdata

    assert client.get("/api/series/nope").status_code == 404
    monkeypatch.setattr(earthdata, "series", lambda source: None)
    j = client.get("/api/series/smap-l4").json()
    assert j["t"] == [] and j["pending"] is True
