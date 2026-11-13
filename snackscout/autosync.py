"""Auto-sync a livestream to the official match times with OpenCV.

A stream's 'went live' timestamp is often a few minutes off. This reads the scoreboard overlay directly
from the YouTube stream (seeking, no full download) around where matches should be, works out when each
match it sees actually started (from the countdown timer), and then finds the single time shift that
lines those starts up with the official match start times.
"""
import threading
from collections import Counter

import cv2
import yt_dlp

from . import cache, db, overlay
from .video import _QuietLogger

AUTO_LEN, TRANSITION = 30, 8
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def stream_url(video_id: str) -> str:
    key = f"streamurl:{video_id}"
    hit = cache.get(key, 3 * 3600)
    if hit:
        return hit
    opts = dict(quiet=True, no_warnings=True, logger=_QuietLogger(),
                format="bv*[height<=480][vcodec^=avc1]/bv*[height<=480]/b[height<=480]")
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return cache.put(key, info["url"])


def start_from_reading(t: float, timer: int | None):
    """Stream time when the match started, from one overlay reading (None if ambiguous)."""
    if timer is None or timer >= 150 or timer < 10:
        return None
    if timer > 122:  # auto counts 2:30 -> 2:00
        return t - (150 - timer)
    if timer < 118:  # teleop counts 2:00 -> 0:00 after the 8 s transition
        return t - AUTO_LEN - TRANSITION - (120 - timer)
    return None


def scan(video_id: str, center: float, span: float = 480, step: float = 20, progress=None):
    cap = cv2.VideoCapture(stream_url(video_id), cv2.CAP_FFMPEG)
    starts = []
    times = [center + k * step for k in range(int(-span / step), int(span / step) + 1)]
    for i, t in enumerate(times):
        if t < 0:
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            s = start_from_reading(t, overlay.read_frame(frame)["timer"])
            if s is not None:
                starts.append(s)
        if progress:
            progress(i + 1, len(times))
    cap.release()
    # merge readings from the same match
    starts.sort()
    merged = []
    for s in starts:
        if merged and abs(s - merged[-1][-1]) < 6:
            merged[-1].append(s)
        else:
            merged.append([s])
    return [sum(g) / len(g) for g in merged if len(g) >= 2 or len(merged) <= 2]


def best_shift(found: list[float], predicted: list[float]):
    """Shift d so that found starts ~= predicted + d for as many matches as possible."""
    votes = Counter()
    for s in found:
        for p in predicted:
            votes[round((s - p) / 3) * 3] += 1
    if not votes:
        return None, 0
    d, _ = votes.most_common(1)[0]
    near = [s - p for s in found for p in predicted if abs(s - p - d) <= 6]
    hits = len({round(s) for s in found if any(abs(s - p - d) <= 6 for p in predicted)})
    return (sum(near) / len(near) if near else d), hits


def run(event_code: str, video_id: str, official_starts: list[float]):
    """official_starts: unix times of played matches at this event."""
    key = f"{event_code}:{video_id}"

    def prog(i, n):
        with _lock:
            _jobs[key] = {"state": "scanning", "done": i, "total": n}
    try:
        vids = {v["video_id"]: v for v in db.event_videos(event_code)}
        meta_start = vids[video_id]["start_ts"]
        cur = vids[video_id]["sync_offset"] or 0
        predicted = sorted(ts - meta_start for ts in official_starts)
        mid = predicted[len(predicted) // 2]
        found = scan(video_id, mid + cur, progress=prog)
        shift, hits = best_shift(found, predicted)
        if shift is None or hits == 0:
            found = scan(video_id, mid + cur, span=1500, step=30, progress=prog)
            shift, hits = best_shift(found, predicted)
        if shift is None or hits == 0:
            state = {"state": "error", "error": "Couldn't find any matches with a readable scoreboard near the expected time."}
        else:
            db.set_sync(event_code, video_id, round(shift, 1))
            state = {"state": "done", "shift": round(shift, 1), "previous": cur, "matches_found": len(found), "matched": hits}
    except Exception as e:  # noqa: BLE001
        state = {"state": "error", "error": str(e)[:300]}
    with _lock:
        _jobs[key] = state


def request(event_code, video_id, official_starts):
    key = f"{event_code}:{video_id}"
    with _lock:
        if _jobs.get(key, {}).get("state") in ("queued", "scanning"):
            return _jobs[key]
        _jobs[key] = {"state": "queued"}
    threading.Thread(target=run, args=(event_code, video_id, official_starts), daemon=True).start()
    return {"state": "queued"}


def status(event_code, video_id):
    with _lock:
        return dict(_jobs.get(f"{event_code}:{video_id}", {"state": "none"}))
