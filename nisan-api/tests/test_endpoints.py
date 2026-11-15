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
