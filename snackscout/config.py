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

# Team code: teammates need it once to create their account. (Stored in .env as TEAM_PASSWORD; once an
# admin changes it in Settings, the team-wide value in the database/cloud wins.)
TEAM_PASSWORD = os.getenv("TEAM_PASSWORD", "")
# Before any account exists, people at this laptop (http://localhost) may create the first admin account.
LOCAL_NO_PASSWORD = os.getenv("LOCAL_NO_PASSWORD", "1") == "1"
HOST = os.getenv("HOST", "0.0.0.0")

# Team cloud (Supabase). The service_role key stays on the laptop/server only; it's never sent to browsers.
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# Slack bot (per laptop: only the laptop with these tokens connects and posts).
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")      # xoxb-...
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")      # xapp-... (Socket Mode)
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")          # where automatic posts go, e.g. #scouting
SLACK_DISABLED = os.getenv("SLACK_DISABLED", "") == "1"  # tests / extra copies


def env_set(key, value):
    """Add or replace one line in .env."""
    p = ROOT / ".env"
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out, done = [], False
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value
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
DB_PATH = Path(os.getenv("SNACKSCOUT_DB") or ROOT / "snackscout.db")  # override only for tests
for d in (CACHE_DIR, CLIPS_DIR, ANALYSIS_DIR):
    d.mkdir(exist_ok=True)

# How much video to grab around each match (seconds relative to match start).
# A BIOBUZZ match is 2:30 plus the 8 s auto->teleop transition; the final score shows a bit after.
CLIP_BEFORE = 10
CLIP_AFTER = 185
CLIP_MAX_HEIGHT = int(os.getenv("CLIP_MAX_HEIGHT", "480"))
