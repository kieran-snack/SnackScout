"""Official FIRST FTC Events API (needs the key in .env). Used for team info and upcoming events."""
import requests

from . import cache
from .config import FTC_EVENTS_TOKEN, FTC_EVENTS_USERNAME, SEASON

BASE = "https://ftc-api.firstinspires.org/v2.0"


def enabled() -> bool:
    return bool(FTC_EVENTS_USERNAME and FTC_EVENTS_TOKEN)


def _get(path, params=None, max_age=30 * 60, refresh=False):
    if not enabled():
        return None
    key = f"ftcevents:{path}:{sorted((params or {}).items())}"
    if not refresh:
        hit = cache.get(key, max_age)
        if hit is not None:
            return hit
    try:
        r = requests.get(BASE + path, params=params, timeout=30,
                         auth=(FTC_EVENTS_USERNAME, FTC_EVENTS_TOKEN))
        if r.status_code != 200:
            return cache.get_stale(key)
        return cache.put(key, r.json())
    except (requests.RequestException, ValueError):
        return cache.get_stale(key)


def team_info(number: int, season: int = SEASON):
    data = _get(f"/{season}/teams", {"teamNumber": number}, max_age=24 * 3600)
    teams = (data or {}).get("teams") or []
    return teams[0] if teams else None


def event_teams(code: str, season: int = SEASON):
    data = _get(f"/{season}/teams", {"eventCode": code}, max_age=3600)
    return (data or {}).get("teams") or []


def schedule(code: str, season: int = SEASON, refresh=False):
    """Qualification + playoff schedule. Checked often because it appears on event day."""
    out = []
    for level in ("qual", "playoff"):
        data = _get(f"/{season}/schedule/{code}", {"tournamentLevel": level}, max_age=60, refresh=refresh)
        out += (data or {}).get("schedule") or []
    return out


def results(code: str, season: int = SEASON, refresh=False):
    data = _get(f"/{season}/matches/{code}", max_age=60, refresh=refresh)
    return (data or {}).get("matches") or []


def team_events(number: int, season: int = SEASON, refresh=False):
    """All events the team is registered for, including future ones FTCScout may not show yet."""
    data = _get(f"/{season}/events", {"teamNumber": number}, refresh=refresh)
    return (data or {}).get("events") or []
