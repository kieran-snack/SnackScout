"""OpenCV match analysis of a downloaded clip.

1. Scoreboard (automatic): reads the official overlay every 0.5 s -> score timeline, auto points,
   hive tip moments, and where the match really starts in the clip (used to auto-fix video sync).
2. Pollen shots (needs the two hive boxes calibrated once per livestream): finds fast-moving yellow
   pollen (HSV colour mask + MOG2 background subtraction), links detections frame-to-frame into
   tracks, and counts a shot when a track rises into a hive box. Shots close together become a
   "burst", saved with a picture showing where it was launched so a scout can say whose shot it was.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from . import overlay
from .config import ANALYSIS_DIR, CLIP_BEFORE, CLIPS_DIR

AUTO_LEN, TRANSITION, TELEOP_LEN = 30, 8, 120
MATCH_LEN = AUTO_LEN + TRANSITION + TELEOP_LEN

_pool = ThreadPoolExecutor(max_workers=1)  # CV is CPU heavy: one match at a time
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- scoreboard
def _debounce(samples, key):
    """Keep a reading only once it's been seen twice in a row and never goes backwards."""
    out, last, cand, seen = [], None, None, 0
    for s in samples:
        v = s[key]
        if v is None:
            continue
        if v == cand:
            seen += 1
        else:
            cand, seen = v, 1
        if seen >= 2 and v != last and (last is None or v >= last):
            out.append((s["t"], v))
            last = v
    return out


def _match_starts(samples):
    """Every match start the scoreboard shows in the clip (a clip can catch the end of the previous match)."""
    starts = []
    for s in samples:
        t = s["timer"]
        if t is None or t >= 150 or t < 10:
            continue
        st = s["t"] - (150 - t) if t > 122 else s["t"] - AUTO_LEN - TRANSITION - (120 - t) if t < 118 else None
        if st is None:
            continue
        if starts and abs(st - starts[-1][-1]) < 6:
            starts[-1].append(st)
        else:
            starts.append([st])
    return [sum(g) / len(g) for g in starts if len(g) >= 2]


def _match_start(samples):
    """Clip time when *this* match starts: the start nearest to where the clip expects it (CLIP_BEFORE s in).
    Picking the first start found used to analyse the previous match when a stream's sync was off."""
    starts = _match_starts(samples)
    if not starts:
        return None
    return min(starts, key=lambda s: abs(s - CLIP_BEFORE))


def _alliance(samples, side, start):
    series = _debounce(samples, side)
    hive = _debounce(samples, f"{side}_hive")
    events, prev = [], 0
    for t, v in series:
        if v > prev:
            events.append(dict(t=round(t - start, 1) if start is not None else None, delta=v - prev, score=v))
        prev = v
    auto = None
    if start is not None:
        before = [v for t, v in series if t <= start + AUTO_LEN + TRANSITION - 1]
        auto = before[-1] if before else 0
    return dict(final=series[-1][1] if series else None, auto=auto, events=events,
                tips=[round(t - start, 1) for t, v in hive[1:]] if start is not None else [])


# ---------------------------------------------------------------- pollen shots
class _ShotTracker:
    def __init__(self, scale):
        self.s = scale
        self.bg = cv2.createBackgroundSubtractorMOG2(history=90, varThreshold=20, detectShadows=False)
        self.live, self.done = [], []

    def step(self, roi, t):
        fg = self.bg.apply(roi)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.bitwise_and(cv2.inRange(hsv, (20, 40, 130), (45, 255, 255)), fg)
        n, _, st, cen = cv2.connectedComponentsWithStats(mask)
        s2 = self.s * self.s
        pts = [tuple(c) for q, c in zip(st[1:], cen[1:]) if 3 * s2 <= q[4] <= 250 * s2]
        used = set()
        for tr in self.live:
            (x, y), (vx, vy) = tr["p"][-1], tr["v"]
            best, bd = None, 30 * self.s
            for j, (qx, qy) in enumerate(pts):
                d = ((qx - x - vx) ** 2 + (qy - y - vy) ** 2) ** 0.5
                if j not in used and d < bd:
                    best, bd = j, d
            if best is None:
                tr["miss"] += 1
            else:
                used.add(best)
                q = pts[best]
                tr["v"] = (q[0] - x, q[1] - y)
                tr["p"].append(q)
                tr["t"].append(t)
                tr["miss"] = 0
        for j, q in enumerate(pts):
            if j not in used:
                self.live.append(dict(p=[q], t=[t], v=(0, 0), miss=0))
        keep = []
        for tr in self.live:
            (self.done if tr["miss"] > 1 else keep).append(tr)
        self.live = keep

    def finish(self):
        self.done += self.live
        self.live = []
        return self.done


def _enters(tr, box, s, tip_times=()):
    p = np.array(tr["p"])
    if len(p) < 2 or (-np.diff(p[:, 1])).mean() <= 3 * s:
        return False
    x0, y0, x1, y1 = box
    starts_inside = x0 <= p[0][0] <= x1 and y0 <= p[0][1] <= y1
    if starts_inside and p[0][1] < y0 + 0.6 * (y1 - y0):
        return False  # began high up in the hive: spectators behind it / hive moving, not a shot
    if starts_inside and any(0 <= tr["t"][0] - tt <= 4 for tt in tip_times):
        return False  # pollen shifting while the hive tips and resets
    inside = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    if not inside.any():
        return False
    k = int(np.argmax(inside))
    from_below = k > 0 and p[0][1] > y1 - 10 * s
    fast = len(p) >= 3 and (-np.diff(p[:, 1])).mean() > 7 * s
    return from_below or fast


def _scaled_box(box, w, h):
    x0, y0, x1, y1 = box
    sx, sy = w / overlay.REF_W, h / overlay.REF_H
    return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)


# ---------------------------------------------------------------- main
def analyze(clip_name: str, hives: dict | None):
    path = CLIPS_DIR / clip_name
    out_dir = ANALYSIS_DIR / clip_name.removesuffix(".mp4")
    out_dir.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = h / overlay.REF_H
    boxes = {side: _scaled_box(b, w, h) for side, b in (hives or {}).items() if b}
    tracker = _ShotTracker(scale) if boxes else None
    every = max(1, int(fps / 2))
    samples, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        if i % every == 0:
            samples.append(dict(t=round(t, 2), **overlay.read_frame(frame)))
        if tracker:
            tracker.step(frame[0:int(h * 0.77)], t)
        i += 1
    duration = i / fps

    start = _match_start(samples)
    overlay_ok = sum(1 for s in samples if s["timer"] is not None) > len(samples) * 0.5
    result = dict(
        clip=clip_name, duration=round(duration, 1), width=w, height=h, overlay_ok=overlay_ok,
        match_start=round(start, 1) if start is not None else None,
        sync_error=round(start - CLIP_BEFORE, 1) if start is not None else None,
        wrong_match=start is None or abs(start - CLIP_BEFORE) > 45,
        red=_alliance(samples, "red", start), blue=_alliance(samples, "blue", start),
        timeline=[[s["t"], s["red"], s["blue"]] for s in samples if s["red"] is not None or s["blue"] is not None],
        hives_calibrated=bool(boxes), shots={}, bursts=[],
    )

    if tracker:
        tracks = tracker.finish()
        lo = (start or 0) - 1
        hi = (start + MATCH_LEN + 2) if start is not None else duration
        for side, box in boxes.items():
            # clip times when this alliance's score jumped by a tip-sized amount
            tips = [e["t"] + (start or 0) for e in result[side]["events"] if e["t"] is not None and e["delta"] >= 20]
            hits = sorted((tr for tr in tracks if lo <= tr["t"][0] <= hi and _enters(tr, box, scale, tips)),
                          key=lambda tr: tr["t"][0])
            result["shots"][side] = [dict(t=round(tr["t"][0] - (start or 0), 1),
                                          x=int(tr["p"][0][0]), y=int(tr["p"][0][1]),
                                          phase=_phase(tr["t"][0] - (start or 0))) for tr in hits]
            groups = []
            for tr in hits:
                if groups and tr["t"][0] - groups[-1][-1]["t"][0] < 1.5:
                    groups[-1].append(tr)
                else:
                    groups.append([tr])
            for g in groups:
                result["bursts"].append(_burst_picture(cap, out_dir, side, g, start or 0, len(result["bursts"])))
        result["bursts"].sort(key=lambda b: b["t"])
    cap.release()
    (ANALYSIS_DIR / (clip_name.removesuffix(".mp4") + ".json")).write_text(json.dumps(result), encoding="utf-8")
    return result


def _phase(mt):
    if mt < AUTO_LEN:
        return "auto"
    if mt < AUTO_LEN + TRANSITION:
        return "transition"
    return "endgame" if mt >= MATCH_LEN - 60 else "teleop"  # nectar can only be scored in the last minute


def _burst_picture(cap, out_dir, side, group, start, idx):
    t0 = group[0]["t"][0]
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t0 - 0.4) * 1000)
    ok, frame = cap.read()
    if ok:
        color = (60, 60, 255) if side == "red" else (255, 140, 40)
        for tr in group:
            pts = np.array(tr["p"], np.int32)
            cv2.polylines(frame, [pts], False, color, 2)
            cv2.circle(frame, tuple(int(v) for v in tr["p"][0]), 14, (0, 255, 255), 2)
        name = f"burst_{idx}.jpg"
        cv2.imwrite(str(out_dir / name), frame)
    else:
        name = None
    return dict(i=idx, side=side, t=round(t0 - start, 1), n=len(group), phase=_phase(t0 - start),
                x=int(group[0]["p"][0][0]), y=int(group[0]["p"][0][1]),
                img=f"/analysis/{out_dir.name}/{name}" if name else None)


# ---------------------------------------------------------------- jobs
def result(clip_name: str):
    p = ANALYSIS_DIR / (clip_name.removesuffix(".mp4") + ".json")
    if p.exists():
        return {"state": "done", "result": json.loads(p.read_text(encoding="utf-8"))}
    with _lock:
        return dict(_jobs.get(clip_name, {"state": "none"}))


def _run(clip_name, hives):
    with _lock:
        _jobs[clip_name] = {"state": "analyzing"}
    try:
        analyze(clip_name, hives)
        state = {"state": "done"}
    except Exception as e:  # noqa: BLE001
        state = {"state": "error", "error": str(e)[:300]}
    with _lock:
        _jobs[clip_name] = state


def request(clip_name: str, hives: dict | None, force=False):
    cur = result(clip_name)
    if cur["state"] in ("analyzing", "queued") or (cur["state"] == "done" and not force):
        return cur
    p = ANALYSIS_DIR / (clip_name.removesuffix(".mp4") + ".json")
    if force and p.exists():
        p.unlink()
    with _lock:
        _jobs[clip_name] = {"state": "queued"}
    _pool.submit(_run, clip_name, hives)
    return {"state": "queued"}


def grab_frame(clip_name: str, t: float):
    cap = cv2.VideoCapture(str(CLIPS_DIR / clip_name))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    frame = cv2.resize(frame, (overlay.REF_W, overlay.REF_H))
    return cv2.imencode(".jpg", frame)[1].tobytes()
