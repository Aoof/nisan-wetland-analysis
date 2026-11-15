"""The webroot is served at the site root, ahead of the built app, and never shadows /api."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import web_files


def make(tmp_path, webroot=True, static=True):
    root, dist = tmp_path / "webroot", tmp_path / "dist"
    if webroot:
        (root / ".well-known" / "acme-challenge").mkdir(parents=True)
        (root / ".well-known" / "acme-challenge" / "tok3n-AbC_9").write_text("tok3n-AbC_9.thumbprint")
        (root / "robots.txt").write_text("User-agent: *\nDisallow:\n")
    if static:
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>NISAN</title>")
        (dist / "robots.txt").write_text("built")
        (dist / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    files = web_files(root if webroot else None, dist if static else None)
    if files:
        app.mount("/", files, name="web")
    return TestClient(app), root


def test_acme_challenge_is_served_as_plain_text(tmp_path):
    c, _ = make(tmp_path)
    r = c.get("/.well-known/acme-challenge/tok3n-AbC_9", follow_redirects=False)
    assert r.status_code == 200 and r.text == "tok3n-AbC_9.thumbprint"
    assert r.headers["content-type"].startswith("text/plain") and r.headers["cache-control"] == "no-store"


def test_tokens_written_after_start_are_served(tmp_path):
    c, root = make(tmp_path)
    assert c.get("/.well-known/acme-challenge/late").status_code == 404
    (root / ".well-known" / "acme-challenge" / "late").write_text("late.thumbprint")
    assert c.get("/.well-known/acme-challenge/late").text == "late.thumbprint"


def test_webroot_wins_then_app_then_api(tmp_path):
    c, _ = make(tmp_path)
    assert c.get("/robots.txt").text.startswith("User-agent")
    assert "NISAN" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/health").json() == {"ok": True}


def test_no_escape_from_the_webroot(tmp_path):
    c, _ = make(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    assert c.get("/../secret.txt").status_code == 404
    assert c.get("/.well-known/../../secret.txt").status_code == 404


def test_webroot_alone_or_nothing(tmp_path):
    c, _ = make(tmp_path, static=False)
    assert c.get("/.well-known/acme-challenge/tok3n-AbC_9").status_code == 200
    assert web_files(None, None) is None
    assert web_files(tmp_path / "missing", None) is None
