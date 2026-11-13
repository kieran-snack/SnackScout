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
