"""The built web app (NISAN_STATIC), served at the site root after every /api route."""
from pathlib import Path

from starlette.staticfiles import StaticFiles


def web_files(static: str | Path | None) -> StaticFiles | None:
    if not static or not Path(static).is_dir():
        return None
    # html=True: "/" serves index.html and a missing path tries 404.html.
    return StaticFiles(directory=static, html=True)
