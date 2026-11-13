"""Finding match footage on YouTube with yt-dlp.

How it works:
  1. For each event, collect candidate livestreams: links listed on the event (FTCScout / FTC Events,
     following redirects like ftcwa.live -> YouTube) plus a YouTube search for the event name.
  2. A livestream VOD knows the moment it went live (release_timestamp). FTCScout knows the exact
     moment each match started (actualStartTime). Subtracting gives the position in the video.
  3. If the video has chapters like "Q12" / "Qual 12", those are used instead.
  4. Each event video has a +/- sync offset you can nudge in the UI if a stream is a bit off.
"""
import re
from datetime import datetime

import requests
import yt_dlp

from . import cache, db
from .config import CLIP_BEFORE

YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
STOPWORDS = {"ftc", "first", "tech", "challenge", "the", "of", "and", "a", "at", "in", "for",
             "biobuzz", "2026", "2027", "event", "presented", "by"}
LIVE_STATES = {"was_live", "post_live", "is_live"}


def ts(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _ydl(**opts):
    base = dict(quiet=True, no_warnings=True, noprogress=True, skip_download=True,
                ignore_no_formats_error=True, logger=_QuietLogger())
    base.update(opts)
    return yt_dlp.YoutubeDL(base)


class _QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def video_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = YT_ID_RE.search(url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    # Short links such as ftcwa.live/2027/... redirect to YouTube.
    try:
        r = requests.get(url, allow_redirects=True, timeout=10, stream=True)
        r.close()
        m = YT_ID_RE.search(r.url)
        if m:
            return m.group(1)
    except requests.RequestException:
        pass
    if "youtube.com" in url:  # e.g. a channel's /live page
        try:
            with _ydl(extract_flat=True) as y:
                info = y.extract_info(url, download=False)
            return info.get("id") if len(info.get("id") or "") == 11 else None
        except yt_dlp.utils.DownloadError:
            return None
    return None


def video_meta(video_id: str, refresh=False) -> dict | None:
    key = f"ytmeta:{video_id}"
    hit = None if refresh else cache.get(key, 7 * 86400)
    if hit and hit.get("live_status") != "is_live":
        return hit
    if hit and cache.get(key, 300):  # still live: re-check every 5 minutes
        return hit
    try:
        with _ydl() as y:
            info = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError:
        return hit
    live = info.get("live_status")
    meta = dict(
        id=info["id"], title=info.get("title") or "", channel=info.get("channel") or "",
        duration=info.get("duration") or 0, live_status=live,
        upload_ts=info.get("release_timestamp") or info.get("timestamp"),
        start_ts=info.get("release_timestamp") if live in LIVE_STATES else None,
        chapters=[dict(t=c.get("title") or "", start=c.get("start_time") or 0) for c in info.get("chapters") or []],
    )
    return cache.put(key, meta)


def yt_search(query: str, n=10) -> list[dict]:
    key = f"ytsearch:{n}:{query}"
    hit = cache.get(key, 6 * 3600)
    if hit is not None:
        return hit
    try:
        with _ydl(extract_flat=True) as y:
            info = y.extract_info(f"ytsearch{n}:{query}", download=False)
    except yt_dlp.utils.DownloadError:
        return cache.get_stale(key) or []
    res = [dict(id=e["id"], title=e.get("title") or "", duration=e.get("duration") or 0,
                channel=e.get("channel") or e.get("uploader") or "")
           for e in info.get("entries") or [] if e and e.get("id")]
    return cache.put(key, res)


def _tokens(s: str):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def title_score(event_name: str, title: str) -> float:
    """How well a video title matches an event name (0..1). Numbers like 'Meet 1' must match exactly."""
    ev = [t for t in _tokens(event_name) if t not in STOPWORDS]
    tt = set(_tokens(title))
    if not ev:
        return 0.0
    if any(t.isdigit() and t not in tt for t in ev):
        return 0.0
    return sum(t in tt for t in ev) / len(ev)


def _event_links(event: dict):
    links = [event.get("liveStreamURL"), *(event.get("webcasts") or [])]
    for day in event.get("livestreamsByDay") or []:
        links += [day.get("liveStreamURL"), *(day.get("webcasts") or [])]
    return [l for l in dict.fromkeys(links) if l]


def _chapter_offset(meta, label: str):
    """Find a chapter like 'Q12', 'Qual 12', 'Qualification 12', 'Match 12' for label 'Q-12'."""
    m = re.fullmatch(r"Q-?(\d+)", label or "")
    if not m or not meta.get("chapters"):
        return None
    n = m.group(1)
    pat = re.compile(rf"\b(q|qm|qual|quals|qualification|match)\s*[-#]?\s*0*{n}\b", re.I)
    for ch in meta["chapters"]:
        if pat.search(ch["t"]):
            return ch["start"]
    return None


def ensure_event_videos(event: dict, match_times: list[float], refresh=False) -> list[dict]:
    """Search once per event (cached) and remember usable livestreams in the database."""
    code = event["code"]
    key = f"evsearch:{code}"
    if refresh or cache.get(key, 6 * 3600) is None:
        cand: dict[str, str] = {}
        for link in _event_links(event):
            vid = video_id_from_url(link)
            if vid:
                cand.setdefault(vid, "event link")
        for q in (f"{event['name']} FTC", f"{event['name']} BioBuzz"):
            for r in yt_search(q, 10):
                long_enough = r["duration"] == 0 or r["duration"] >= 1800
                if long_enough and title_score(event["name"], r["title"]) >= 0.6:
                    cand.setdefault(r["id"], "youtube search")
        lo = min(match_times) - 3600 if match_times else None
        hi = max(match_times) + 3600 if match_times else None
        for vid, source in list(cand.items())[:6]:
            meta = video_meta(vid, refresh=refresh)
            if not meta:
                continue
            ok = False
            if meta["start_ts"] and lo is not None:
                v_end = meta["start_ts"] + (meta["duration"] or 12 * 3600)
                ok = meta["start_ts"] < hi and v_end > lo  # stream overlaps the event's matches
            # A normal upload with "Q12"-style chapters: must be posted around the event (not an old season).
            posted = meta.get("upload_ts")
            ev_start = ts(event["start"] + "T00:00:00Z")
            if (meta["chapters"] and posted and ev_start and ev_start - 86400 <= posted <= ev_start + 45 * 86400
                    and title_score(event["name"], meta["title"]) >= 0.6):
                ok = True
            if source == "event link" and meta["start_ts"]:
                ok = ok or lo is None
            if ok:
                db.add_event_video(code, meta, source)
        cache.put(key, True)
    return db.event_videos(code)


def locate(event_videos: list[dict], label: str, match_ts: float | None):
    """Return where in which video a match is, or None."""
    priority = {"manual": 0, "event link": 1, "youtube search": 2}
    for v in sorted(event_videos, key=lambda v: priority.get(v.get("source"), 3)):
        meta = video_meta(v["video_id"])
        if not meta:
            continue
        off = _chapter_offset(meta, label)
        method = "chapter"
        if off is None and match_ts and meta.get("start_ts"):
            off = match_ts - meta["start_ts"]
            method = "timestamp"
            dur = meta.get("duration") or 0
            if off < -120 or (dur and off > dur):
                off = None
        if off is None:
            continue
        off = max(0, off + (v.get("sync_offset") or 0))
        start = max(0, int(off - CLIP_BEFORE))
        return dict(video_id=v["video_id"], offset=int(off), start=start, method=method,
                    title=meta["title"], url=f"https://www.youtube.com/watch?v={v['video_id']}&t={start}s")
    return None


def team_videos(number: int, name: str) -> list[dict]:
    """Robot reveals, match uploads, etc. that mention the team."""
    seen, out = set(), []
    for q in (f"FTC {number} {name} BioBuzz", f"FTC {number} robot"):
        for r in yt_search(q, 10):
            hay = f"{r['title']} {r['channel']}".lower()
            if r["id"] in seen:
                continue
            if re.search(rf"\b{number}\b", hay) or (len(name) > 3 and name.lower() in hay):
                seen.add(r["id"])
                r = dict(r, url=f"https://www.youtube.com/watch?v={r['id']}",
                         this_season="biobuzz" in hay or "bio buzz" in hay)
                out.append(r)
    out.sort(key=lambda r: not r["this_season"])
    return out
