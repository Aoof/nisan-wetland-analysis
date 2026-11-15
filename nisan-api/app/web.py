"""Files served at the site root, after every /api route.

Two layers, looked up in order:
  1. the webroot (NISAN_WEBROOT): a folder you mount and drop files into at runtime, e.g.
     .well-known/acme-challenge/<token> for Let's Encrypt HTTP-01, robots.txt, verification files.
     A file here wins over a built file with the same path.
  2. the built web app (NISAN_STATIC).
"""
from pathlib import Path

from starlette.staticfiles import StaticFiles
from starlette.types import Scope

ACME = "/.well-known/acme-challenge/"


class WebFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope: Scope, status_code: int = 200):
        r = super().file_response(full_path, stat_result, scope, status_code)
        if scope["path"].startswith(ACME):
            # Challenge tokens have no extension; say what they are and never let a proxy cache one.
            r.headers["content-type"] = "text/plain; charset=utf-8"
            r.headers["cache-control"] = "no-store"
        return r


def web_files(webroot: str | Path | None, static: str | Path | None) -> WebFiles | None:
    layers = [Path(d) for d in (webroot, static) if d and Path(d).is_dir()]
    if not layers:
        return None
    # html=True: "/" serves index.html and a missing path tries 404.html, from whichever layer has it first.
    files = WebFiles(directory=layers[0], html=True)
    files.all_directories = [*files.all_directories, *layers[1:]]
    return files
