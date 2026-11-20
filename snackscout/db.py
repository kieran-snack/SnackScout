"""Local SQLite storage: accounts, scouting notes, robot notes, livestream settings, OpenCV labels.

Every shared row carries `updated` (time), `updated_by` (username) and `synced` (0 = not uploaded to the
team cloud yet). The cloud module uploads unsynced rows and downloads teammates' changes.
"""
import contextvars
import json
import sqlite3
import time
from contextlib import contextmanager

from werkzeug.security import check_password_hash, generate_password_hash

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS match_notes (
  team INTEGER, event_code TEXT, match_id INTEGER, match_label TEXT,
  auto_pollen INTEGER, teleop_pollen INTEGER, nectar INTEGER, hive_tips INTEGER,
  missed INTEGER, scored_where TEXT, park TEXT, defense INTEGER, broke_down INTEGER,
  rating INTEGER, notes TEXT, scouter TEXT, updated REAL,
  PRIMARY KEY (team, event_code, match_id)
);
CREATE TABLE IF NOT EXISTS team_notes (
  team INTEGER PRIMARY KEY, drivetrain TEXT, shooter TEXT, elements TEXT,
  auto_desc TEXT, strengths TEXT, weaknesses TEXT, notes TEXT, updated REAL
);
CREATE TABLE IF NOT EXISTS event_videos (
  event_code TEXT, video_id TEXT, title TEXT, start_ts REAL, duration REAL,
  sync_offset REAL DEFAULT 0, source TEXT, hidden INTEGER DEFAULT 0,
  PRIMARY KEY (event_code, video_id)
);
CREATE TABLE IF NOT EXISTS video_calib (
  video_id TEXT PRIMARY KEY, red TEXT, blue TEXT
);
CREATE TABLE IF NOT EXISTS shot_labels (
  clip TEXT, burst INTEGER, team INTEGER, event_code TEXT, match_id INTEGER,
  n INTEGER, phase TEXT, label TEXT, PRIMARY KEY (clip, burst, team)
);
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, display_name TEXT, pw_hash TEXT, role TEXT DEFAULT 'member',
  created REAL, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS prefs (
  username TEXT PRIMARY KEY, data TEXT
);
CREATE TABLE IF NOT EXISTS team_config (
  key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY, value TEXT
);
"""

# table -> primary key columns. All of these sync to the team cloud.
SYNCED = {
    "match_notes": ("team", "event_code", "match_id"),
    "team_notes": ("team",),
    "event_videos": ("event_code", "video_id"),
    "video_calib": ("video_id",),
    "shot_labels": ("clip", "burst", "team"),
    "users": ("username",),
    "prefs": ("username",),
    "team_config": ("key",),
}

MATCH_FIELDS = ["auto_pollen", "teleop_pollen", "nectar", "hive_tips", "missed", "scored_where",
                "park", "defense", "broke_down", "rating", "notes", "scouter"]
TEAM_FIELDS = ["drivetrain", "shooter", "elements", "auto_desc", "strengths", "weaknesses", "notes"]

_actor = contextvars.ContextVar("actor", default=None)
_on_change = []  # callbacks (the cloud module wakes up when something changes)


def set_actor(username):
    """Who is making changes in this request (stored as updated_by)."""
    _actor.set(username)


def on_change(fn):
    _on_change.append(fn)


def _changed():
    for fn in _on_change:
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        for table in SYNCED:  # upgrade older databases in place
            cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            for col, decl in (("updated", "REAL"), ("updated_by", "TEXT"), ("synced", "INTEGER DEFAULT 0")):
                if col not in cols:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            c.execute(f"UPDATE {table} SET updated = ? WHERE updated IS NULL", (time.time(),))


def _stamp():
    return {"updated": time.time(), "updated_by": _actor.get(), "synced": 0}


def _upsert(c, table, row: dict):
    row = {**row, **_stamp()}
    cols = list(row)
    keys = SYNCED[table]
    c.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
              f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET "
              + ", ".join(f"{k}=excluded.{k}" for k in cols if k not in keys), list(row.values()))


def _update(c, table, where: dict, changes: dict):
    changes = {**changes, **_stamp()}
    c.execute(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in changes)} WHERE "
              + " AND ".join(f"{k}=?" for k in where), [*changes.values(), *where.values()])


# ---------------------------------------------------------------- match notes
def match_notes(team: int):
    with conn() as c:
        rows = c.execute("SELECT * FROM match_notes WHERE team=?", (team,)).fetchall()
    return {(r["event_code"], r["match_id"]): dict(r) for r in rows}


def save_match_note(team, event_code, match_id, match_label, values: dict):
    with conn() as c:
        _upsert(c, "match_notes", {"team": team, "event_code": event_code, "match_id": match_id,
                                   "match_label": match_label, **{k: values.get(k) for k in MATCH_FIELDS}})
    _changed()


# ---------------------------------------------------------------- team notes
def team_note(team: int):
    with conn() as c:
        r = c.execute("SELECT * FROM team_notes WHERE team=?", (team,)).fetchone()
    return dict(r) if r else {}


def save_team_note(team, values: dict):
    with conn() as c:
        _upsert(c, "team_notes", {"team": team, **{k: values.get(k) for k in TEAM_FIELDS}})
    _changed()


# ---------------------------------------------------------------- event livestreams
def event_videos(event_code: str, include_hidden=False):
    with conn() as c:
        q = "SELECT * FROM event_videos WHERE event_code=?" + ("" if include_hidden else " AND hidden=0")
        return [dict(r) for r in c.execute(q + " ORDER BY start_ts", (event_code,)).fetchall()]


def add_event_video(event_code, meta: dict, source: str):
    with conn() as c:
        exists = c.execute("SELECT 1 FROM event_videos WHERE event_code=? AND video_id=?",
                           (event_code, meta["id"])).fetchone()
        if exists:
            if source == "manual":  # re-adding by hand un-hides it
                _update(c, "event_videos", {"event_code": event_code, "video_id": meta["id"]},
                        {"hidden": 0, "source": "manual"})
        else:
            _upsert(c, "event_videos", {"event_code": event_code, "video_id": meta["id"], "title": meta["title"],
                                        "start_ts": meta["start_ts"], "duration": meta["duration"],
                                        "sync_offset": 0, "source": source, "hidden": 0})
    _changed()


def set_sync(event_code, video_id, offset: float):
    with conn() as c:
        _update(c, "event_videos", {"event_code": event_code, "video_id": video_id}, {"sync_offset": offset})
    _changed()


def hide_video(event_code, video_id):
    with conn() as c:
        _update(c, "event_videos", {"event_code": event_code, "video_id": video_id}, {"hidden": 1})
    _changed()


def shift_sync(event_code, video_id, delta: float):
    with conn() as c:
        r = c.execute("SELECT sync_offset FROM event_videos WHERE event_code=? AND video_id=?",
                      (event_code, video_id)).fetchone()
        if r:
            _update(c, "event_videos", {"event_code": event_code, "video_id": video_id},
                    {"sync_offset": (r["sync_offset"] or 0) + delta})
    _changed()


# ---------------------------------------------------------------- OpenCV: hive boxes and shot labels
def calibration(video_id):
    with conn() as c:
        r = c.execute("SELECT red, blue FROM video_calib WHERE video_id=?", (video_id,)).fetchone()
    if not r or not r["red"]:
        return None
    return {"red": json.loads(r["red"]), "blue": json.loads(r["blue"])}


def save_calibration(video_id, red, blue):
    with conn() as c:
        _upsert(c, "video_calib", {"video_id": video_id, "red": json.dumps(red), "blue": json.dumps(blue)})
    _changed()


def shot_labels(clip, team):
    with conn() as c:
        rows = c.execute("SELECT burst, label FROM shot_labels WHERE clip=? AND team=? AND label IS NOT NULL",
                         (clip, team)).fetchall()
    return {r["burst"]: r["label"] for r in rows}


def save_shot_label(clip, burst, team, event_code, match_id, n, phase, label):
    with conn() as c:
        _upsert(c, "shot_labels", {"clip": clip, "burst": burst, "team": team, "event_code": event_code,
                                   "match_id": match_id, "n": n, "phase": phase, "label": label})
    _changed()


def clear_shot_labels(clip):
    """Burst numbers change when a clip is re-analysed, so old labels are blanked (kept as rows so the cloud agrees)."""
    with conn() as c:
        for r in c.execute("SELECT burst, team FROM shot_labels WHERE clip=? AND label IS NOT NULL", (clip,)).fetchall():
            _update(c, "shot_labels", {"clip": clip, "burst": r["burst"], "team": r["team"]}, {"label": None})
    _changed()


def team_shots(team):
    """Per match: shots the scouts confirmed were this robot's, split auto / rest."""
    with conn() as c:
        rows = c.execute("""SELECT event_code, match_id,
                              SUM(CASE WHEN label='ours' THEN n ELSE 0 END) shots,
                              SUM(CASE WHEN label='ours' AND phase='auto' THEN n ELSE 0 END) auto_shots,
                              SUM(CASE WHEN label='ours' AND phase='endgame' THEN n ELSE 0 END) endgame_shots
                            FROM shot_labels WHERE team=? AND label IS NOT NULL
                            GROUP BY event_code, match_id HAVING SUM(CASE WHEN label IS NOT NULL THEN 1 ELSE 0 END) > 0""",
                         (team,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- accounts
def norm_username(u):
    return (u or "").strip().lower()


def user_count():
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE deleted=0").fetchone()[0]


def get_user(username):
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE username=? AND deleted=0", (norm_username(username),)).fetchone()
    return dict(r) if r else None


def list_users():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT username, display_name, role, created, updated FROM users WHERE deleted=0 ORDER BY role, display_name")]


def create_user(username, display_name, password, role="member"):
    u = norm_username(username)
    with conn() as c:
        old = c.execute("SELECT deleted FROM users WHERE username=?", (u,)).fetchone()
        if old and not old["deleted"]:
            raise ValueError("That username is taken.")
        _upsert(c, "users", {"username": u, "display_name": display_name.strip() or u,
                             "pw_hash": generate_password_hash(password), "role": role,
                             "created": time.time(), "deleted": 0})
    _changed()
    return get_user(u)


def check_login(username, password):
    u = get_user(username)
    if u and u["pw_hash"] and check_password_hash(u["pw_hash"], password or ""):
        return u
    return None


def update_user(username, **changes):
    allowed = {k: v for k, v in changes.items() if k in ("display_name", "role", "deleted")}
    if "password" in changes:
        allowed["pw_hash"] = generate_password_hash(changes["password"])
    with conn() as c:
        _update(c, "users", {"username": norm_username(username)}, allowed)
    _changed()


def admin_count():
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE deleted=0 AND role='admin'").fetchone()[0]


# ---------------------------------------------------------------- per-person settings
def get_prefs(username):
    if not username:
        return {}
    with conn() as c:
        r = c.execute("SELECT data FROM prefs WHERE username=?", (username,)).fetchone()
    try:
        return json.loads(r["data"]) if r and r["data"] else {}
    except ValueError:
        return {}


def save_prefs(username, data: dict):
    with conn() as c:
        _upsert(c, "prefs", {"username": username, "data": json.dumps(data)})
    _changed()


# ---------------------------------------------------------------- team-wide settings (shared through the cloud)
def team_config(key, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM team_config WHERE key=?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else default


def set_team_config(key, value):
    with conn() as c:
        _upsert(c, "team_config", {"key": key, "value": value})
    _changed()


# ---------------------------------------------------------------- local-only bookkeeping
def meta_get(key, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def meta_set(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
