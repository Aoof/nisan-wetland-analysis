"""Tiny atomic JSON store plus a status registry that every endpoint reports."""
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import DATA

_lock = threading.Lock()
_status: dict[str, dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def set_status(source: str, state: str, message: str = "", newest: str | None = None, **extra) -> None:
    """state: live | refreshing | awaiting-data | unavailable | error"""
    with _lock:
        prev = _status.get(source, {})
        _status[source] = {**prev, "state": state, "message": message, "updated_at": now_iso(), **extra}
        if newest:
            _status[source]["newest"] = newest
        write_json(DATA / "status.json", _status)


def load_status() -> None:
    with _lock:
        _status.update(read_json(DATA / "status.json", {}) or {})


def get_status() -> dict[str, dict[str, Any]]:
    with _lock:
        return json.loads(json.dumps(_status))
