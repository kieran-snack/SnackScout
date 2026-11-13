"""Local SQLite storage for scouter notes and livestream links/sync settings."""
import json
import sqlite3
import time
from contextlib import contextmanager

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
"""

MATCH_FIELDS = ["auto_pollen", "teleop_pollen", "nectar", "hive_tips", "missed", "scored_where",
                "park", "defense", "broke_down", "rating", "notes", "scouter"]
TEAM_FIELDS = ["drivetrain", "shooter", "elements", "auto_desc", "strengths", "weaknesses", "notes"]


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


# ---- match notes ----
def match_notes(team: int):
    with conn() as c:
        rows = c.execute("SELECT * FROM match_notes WHERE team=?", (team,)).fetchall()
    return {(r["event_code"], r["match_id"]): dict(r) for r in rows}


def save_match_note(team, event_code, match_id, match_label, values: dict):
    vals = {k: values.get(k) for k in MATCH_FIELDS}
    with conn() as c:
        c.execute(
            f"INSERT OR REPLACE INTO match_notes (team, event_code, match_id, match_label, "
            f"{', '.join(MATCH_FIELDS)}, updated) VALUES (?,?,?,?,{','.join('?' * len(MATCH_FIELDS))},?)",
            (team, event_code, match_id, match_label, *vals.values(), time.time()))


# ---- team notes ----
def team_note(team: int):
    with conn() as c:
        r = c.execute("SELECT * FROM team_notes WHERE team=?", (team,)).fetchone()
    return dict(r) if r else {}


def save_team_note(team, values: dict):
    vals = [values.get(k) for k in TEAM_FIELDS]
    with conn() as c:
        c.execute(f"INSERT OR REPLACE INTO team_notes (team, {', '.join(TEAM_FIELDS)}, updated) "
                  f"VALUES (?,{','.join('?' * len(TEAM_FIELDS))},?)", (team, *vals, time.time()))


# ---- event livestreams ----
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
                c.execute("UPDATE event_videos SET hidden=0, source='manual' WHERE event_code=? AND video_id=?",
                          (event_code, meta["id"]))
            return
        c.execute("INSERT INTO event_videos VALUES (?,?,?,?,?,0,?,0)",
                  (event_code, meta["id"], meta["title"], meta["start_ts"], meta["duration"], source))


def set_sync(event_code, video_id, offset: float):
    with conn() as c:
        c.execute("UPDATE event_videos SET sync_offset=? WHERE event_code=? AND video_id=?",
                  (offset, event_code, video_id))


def hide_video(event_code, video_id):
    with conn() as c:
        c.execute("UPDATE event_videos SET hidden=1 WHERE event_code=? AND video_id=?", (event_code, video_id))


def shift_sync(event_code, video_id, delta: float):
    with conn() as c:
        c.execute("UPDATE event_videos SET sync_offset = sync_offset + ? WHERE event_code=? AND video_id=?",
                  (delta, event_code, video_id))


# ---- OpenCV: hive boxes per livestream, and scouts' shot labels ----
def calibration(video_id):
    with conn() as c:
        r = c.execute("SELECT red, blue FROM video_calib WHERE video_id=?", (video_id,)).fetchone()
    if not r:
        return None
    return {"red": json.loads(r["red"]), "blue": json.loads(r["blue"])}


def save_calibration(video_id, red, blue):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO video_calib VALUES (?,?,?)", (video_id, json.dumps(red), json.dumps(blue)))


def shot_labels(clip, team):
    with conn() as c:
        rows = c.execute("SELECT burst, label FROM shot_labels WHERE clip=? AND team=?", (clip, team)).fetchall()
    return {r["burst"]: r["label"] for r in rows}


def save_shot_label(clip, burst, team, event_code, match_id, n, phase, label):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO shot_labels VALUES (?,?,?,?,?,?,?,?)",
                  (clip, burst, team, event_code, match_id, n, phase, label))


def clear_shot_labels(clip):
    with conn() as c:
        c.execute("DELETE FROM shot_labels WHERE clip=?", (clip,))


def team_shots(team):
    """Per match: shots the scouts confirmed were this robot's, split auto / rest."""
    with conn() as c:
        rows = c.execute("""SELECT event_code, match_id,
                              SUM(CASE WHEN label='ours' THEN n ELSE 0 END) shots,
                              SUM(CASE WHEN label='ours' AND phase='auto' THEN n ELSE 0 END) auto_shots,
                              SUM(CASE WHEN label='ours' AND phase='endgame' THEN n ELSE 0 END) endgame_shots
                            FROM shot_labels WHERE team=? GROUP BY event_code, match_id""", (team,)).fetchall()
    return [dict(r) for r in rows]
