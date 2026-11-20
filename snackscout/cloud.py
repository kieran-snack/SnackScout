"""Team cloud sync with Supabase.

Every laptop keeps working from its own SQLite copy (works at venues with no internet). In the background:
  push: rows changed here (synced=0) are upserted into one Supabase table, `records`
  pull: rows other laptops changed since our last pull are copied in, if they're newer than ours
The Supabase table keeps the newest version of each row (a trigger ignores older writes), and stamps
`synced_at` on every change so pulls only fetch what's new.
"""
import json
import threading
import time
from datetime import datetime, timedelta

import requests

from . import db
from .config import ROOT, SUPABASE_KEY, SUPABASE_URL

TABLE = "records"
INTERVAL = 20  # seconds between background syncs
_state = {"configured": False, "ok": None, "error": None, "last_sync": None, "pushed": 0, "pulled": 0, "running": False}
_wake = threading.Event()
_lock = threading.Lock()
_cfg = {"url": SUPABASE_URL.rstrip("/"), "key": SUPABASE_KEY}

SCHEMA_SQL = (ROOT / "supabase" / "schema.sql")


def configured():
    return bool(_cfg["url"] and _cfg["key"])


def _headers(extra=None):
    h = {"apikey": _cfg["key"], "Authorization": f"Bearer {_cfg['key']}", "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def _rid(table, row):
    return ":".join(str(row[k]) for k in db.SYNCED[table])


def test(url=None, key=None):
    """Check a URL/key pair and that the records table exists. Returns (ok, message)."""
    url = (url or _cfg["url"]).rstrip("/")
    key = key or _cfg["key"]
    if not url or not key:
        return False, "Not set up yet."
    try:
        r = requests.get(f"{url}/rest/v1/{TABLE}?select=kind&limit=1", timeout=10,
                         headers={"apikey": key, "Authorization": f"Bearer {key}"})
    except requests.RequestException as e:
        return False, f"Can't reach Supabase: {e.__class__.__name__}. Check the URL and the internet."
    if r.status_code == 200:
        return True, "Connected."
    if r.status_code in (401, 403):
        return False, "Supabase rejected the key. Use the service_role key (Project Settings → API)."
    if r.status_code == 404 or "does not exist" in r.text or "PGRST205" in r.text:
        return False, "Connected, but the 'records' table is missing. Run supabase/schema.sql in the SQL Editor."
    return False, f"Supabase error {r.status_code}: {r.text[:160]}"


def configure(url, key):
    """Save cloud settings to .env and switch to them right away."""
    from .config import env_set
    env_set("SUPABASE_URL", url.strip().rstrip("/"))
    env_set("SUPABASE_KEY", key.strip())
    _cfg.update(url=url.strip().rstrip("/"), key=key.strip())
    db.meta_set("cloud_pulled_until", "")  # fresh project: pull everything
    _state["configured"] = True
    wake()


# ---------------------------------------------------------------- push / pull
def _push():
    sent = 0
    for table in db.SYNCED:
        with db.conn() as c:
            rows = [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE synced=0 LIMIT 500")]
        if not rows:
            continue
        payload = [{"kind": table, "id": _rid(table, r),
                    "data": {k: v for k, v in r.items() if k not in ("synced",)},
                    "updated": r["updated"] or time.time(), "updated_by": r.get("updated_by"),
                    "deleted": bool(r.get("deleted") or 0)} for r in rows]
        resp = requests.post(f"{_cfg['url']}/rest/v1/{TABLE}?on_conflict=kind,id", data=json.dumps(payload),
                             headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}), timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"upload failed ({resp.status_code}): {resp.text[:200]}")
        with db.conn() as c:  # mark uploaded, unless it changed again while we were uploading
            for r in rows:
                c.execute(f"UPDATE {table} SET synced=1 WHERE "
                          + " AND ".join(f"{k}=?" for k in db.SYNCED[table]) + " AND updated=?",
                          [*(r[k] for k in db.SYNCED[table]), r["updated"]])
        sent += len(rows)
    return sent


def _apply(c, table, data):
    """Write a teammate's row locally if it's newer than ours."""
    keys = db.SYNCED[table]
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
    data = {k: v for k, v in data.items() if k in cols}
    if any(k not in data for k in keys):
        return False
    mine = c.execute(f"SELECT updated FROM {table} WHERE " + " AND ".join(f"{k}=?" for k in keys),
                     [data[k] for k in keys]).fetchone()
    if mine and (mine["updated"] or 0) >= (data.get("updated") or 0):
        return False
    data["synced"] = 1
    names = list(data)
    c.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))}) "
              f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET "
              + ", ".join(f"{k}=excluded.{k}" for k in names if k not in keys), list(data.values()))
    return True


def _pull():
    got = 0
    since = db.meta_get("cloud_pulled_until") or "1970-01-01T00:00:00+00:00"
    try:  # re-check the last 10 s: a save committing during our last download could carry a slightly older stamp
        since = (datetime.fromisoformat(since) - timedelta(seconds=10)).isoformat()
    except ValueError:
        since = "1970-01-01T00:00:00+00:00"
    while True:
        resp = requests.get(f"{_cfg['url']}/rest/v1/{TABLE}", timeout=30, headers=_headers(),
                            params={"select": "kind,id,data,updated,synced_at", "synced_at": f"gt.{since}",
                                    "order": "synced_at.asc", "limit": "1000"})
        if resp.status_code >= 300:
            raise RuntimeError(f"download failed ({resp.status_code}): {resp.text[:200]}")
        rows = resp.json()
        if not rows:
            break
        with db.conn() as c:
            for r in rows:
                if r["kind"] in db.SYNCED and isinstance(r["data"], dict):
                    got += _apply(c, r["kind"], {**r["data"], "updated": r["updated"]})
        since = rows[-1]["synced_at"]
        db.meta_set("cloud_pulled_until", since)
        if len(rows) < 1000:
            break
    return got


def sync_now():
    if not configured():
        return dict(_state, configured=False)
    with _lock:
        _state["running"] = True
        try:
            pushed = _push()
            pulled = _pull()
            _state.update(ok=True, error=None, last_sync=time.time(), pushed=_state["pushed"] + pushed,
                          pulled=_state["pulled"] + pulled)
        except Exception as e:  # noqa: BLE001 - offline at a venue is normal; we retry
            _state.update(ok=False, error=str(e)[:300] if not isinstance(e, requests.RequestException)
                          else "No connection to the team cloud right now. Changes are saved here and will upload later.")
        finally:
            _state["running"] = False
    return status()


def pending():
    n = 0
    with db.conn() as c:
        for table in db.SYNCED:
            n += c.execute(f"SELECT COUNT(*) FROM {table} WHERE synced=0").fetchone()[0]
    return n


def status():
    return dict(_state, configured=configured(), pending=pending(),
                url=_cfg["url"], ago=int(time.time() - _state["last_sync"]) if _state["last_sync"] else None)


def wake():
    _wake.set()


def _loop():
    while True:
        _wake.wait(INTERVAL)
        _wake.clear()
        time.sleep(1.5)  # gather a few quick edits into one upload
        if configured():
            sync_now()


def start():
    _state["configured"] = configured()
    db.on_change(wake)
    threading.Thread(target=_loop, daemon=True, name="cloud-sync").start()
    wake()
