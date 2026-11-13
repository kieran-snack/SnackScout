"""Background downloads of single-match clips (so footage works offline at competitions)."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from yt_dlp.utils import download_range_func

from .config import CLIP_AFTER, CLIP_BEFORE, CLIP_MAX_HEIGHT, CLIPS_DIR, YTDLP_EXTRA
from .video import _QuietLogger

_pool = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def clip_name(event_code: str, label: str, video_id: str, start: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", f"{event_code}_{label}")
    return f"{safe}_{video_id}_{start}.mp4"


def status(name: str) -> dict:
    if (CLIPS_DIR / name).exists():
        return {"state": "done", "url": f"/clips/{name}"}
    with _lock:
        return dict(_jobs.get(name, {"state": "none"}))


def _download(name: str, video_id: str, start: int, end: int):
    with _lock:
        _jobs[name] = {"state": "downloading"}
    h = CLIP_MAX_HEIGHT
    opts = dict(
        quiet=True, no_warnings=True, noprogress=True, logger=_QuietLogger(), **YTDLP_EXTRA,
        format=f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}]/bv*[height<={h}]+ba/b",
        download_ranges=download_range_func(None, [(start, end)]),
        force_keyframes_at_cuts=True, merge_output_format="mp4",
        outtmpl=str(CLIPS_DIR / name.removesuffix(".mp4")) + ".%(ext)s", overwrites=True,
    )
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([f"https://www.youtube.com/watch?v={video_id}"])
        state = {"state": "done", "url": f"/clips/{name}"} if (CLIPS_DIR / name).exists() \
            else {"state": "error", "error": "download finished but no mp4 was produced"}
    except Exception as e:  # noqa: BLE001 - show any failure in the UI
        state = {"state": "error", "error": str(e)[:300]}
    with _lock:
        _jobs[name] = state


def request(event_code: str, label: str, video_id: str, offset: int) -> dict:
    start = max(0, int(offset) - CLIP_BEFORE)
    name = clip_name(event_code, label, video_id, start)
    st = status(name)
    if st["state"] in ("done", "downloading", "queued"):
        return dict(st, name=name)
    with _lock:
        _jobs[name] = {"state": "queued"}
    _pool.submit(_download, name, video_id, start, int(offset) + CLIP_AFTER)
    return {"state": "queued", "name": name}
