"""Settings loaded from the .env file in the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SEASON = int(os.getenv("FTC_SEASON", "2026"))  # 2026 = 2026-27 BIOBUZZ
FTC_EVENTS_USERNAME = os.getenv("FTC_EVENTS_USERNAME", "")
FTC_EVENTS_TOKEN = os.getenv("FTC_EVENTS_TOKEN", "")
OUR_TEAM = os.getenv("OUR_TEAM_NUMBER", "")

# Optional: a cookies.txt exported from a browser logged in to YouTube. Cloud servers sometimes get
# "Sign in to confirm you're not a bot" from YouTube; cookies usually fix that. Use a throwaway account.
YTDLP_EXTRA = {"cookiefile": os.getenv("YTDLP_COOKIES")} if os.getenv("YTDLP_COOKIES") else {}

# Web hosting: when TEAM_PASSWORD is set, every page needs the password first.
TEAM_PASSWORD = os.getenv("TEAM_PASSWORD", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))


def secret_key() -> str:
    """Key that signs login cookies. Read from .env, else created once and kept in .secret_key."""
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    p = ROOT / ".secret_key"
    if not p.exists():
        import secrets
        p.write_text(secrets.token_hex(32), encoding="utf-8")
    return p.read_text(encoding="utf-8").strip()

CACHE_DIR = ROOT / "cache"
CLIPS_DIR = ROOT / "clips"
ANALYSIS_DIR = ROOT / "analysis"
DB_PATH = ROOT / "snackscout.db"
for d in (CACHE_DIR, CLIPS_DIR, ANALYSIS_DIR):
    d.mkdir(exist_ok=True)

# How much video to grab around each match (seconds relative to match start).
# A BIOBUZZ match is 2:30 plus the 8 s auto->teleop transition; the final score shows a bit after.
CLIP_BEFORE = 10
CLIP_AFTER = 185
CLIP_MAX_HEIGHT = int(os.getenv("CLIP_MAX_HEIGHT", "480"))
