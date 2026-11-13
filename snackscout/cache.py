"""Tiny JSON file cache so repeat lookups are instant and work on bad venue Wi-Fi."""
import hashlib
import json
import time

from .config import CACHE_DIR


def _path(key: str):
    return CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")


def get(key: str, max_age: float | None):
    """Return cached value, or None if missing/expired. max_age=None means never expire."""
    p = _path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if max_age is not None and time.time() - data["t"] > max_age:
        return None
    return data["v"]


def get_stale(key: str):
    """Return a cached value no matter how old (used when we're offline)."""
    return get(key, None)


def put(key: str, value):
    _path(key).write_text(json.dumps({"t": time.time(), "v": value}), encoding="utf-8")
    return value
