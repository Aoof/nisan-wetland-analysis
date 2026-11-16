"""The built app is served at the site root and never shadows /api."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import web_files


def make(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>NISAN</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    app.mount("/", web_files(dist), name="web")
    return TestClient(app)


def test_app_then_api(tmp_path):
    c = make(tmp_path)
    assert "NISAN" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/health").json() == {"ok": True}


def test_no_escape_from_the_app_folder(tmp_path):
    c = make(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    assert c.get("/../secret.txt").status_code == 404


def test_missing_folder_serves_nothing(tmp_path):
    assert web_files(None) is None
    assert web_files(tmp_path / "missing") is None
