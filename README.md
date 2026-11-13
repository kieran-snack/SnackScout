# 🍿 SnackScout

Alliance-partner scouting for FTC team **Snack Time** (2026-27 BIOBUZZ).
Type a team number or name and get a scouting report with every match, a link that jumps straight to that match in the event livestream, and downloadable match clips.

## Start it

Double-click **`SnackScout.bat`**. The first run sets everything up, then your browser opens http://localhost:5000.

Other devices on the same Wi-Fi can open `http://<this-laptop's-IP>:5000`.

Needs Python 3.11+ and ffmpeg on PATH. yt-dlp is installed automatically into `.venv`.

## What it does

| Section | Source |
|---|---|
| OPR, world rank, record, per-event rank | FTCScout |
| Each match: score, auto/teleop, hive tips, pollen+nectar in hive, garden, flower, penalties, RPs | FTCScout (official scores) |
| **This robot's** auto leave, auto park, endgame park | Official per-station scores |
| Upcoming events | FTC Events API |
| ▶ Jump to the match in the livestream | yt-dlp finds the event stream and lines it up with official match start times |
| ⬇ Match clip (watch offline) | yt-dlp + ffmpeg download only that 3-minute piece into `clips/` |
| Pollen/nectar per robot, accuracy, defense, breakdowns | **Your scouts**, using the Scout form next to each clip |
| Side-by-side partner comparison | Type `16750, 3231` in the search box |

Official FTC data only counts pollen, nectar, and hive tips **per alliance**, so the per-robot pollen counts come from the scouting form.

### If a video is wrong or missing
Below each event's match table, open **"Livestreams used for this event"**:
- **Add stream**: paste the event's YouTube livestream (or a link like ftcwa.live that redirects to it).
- **sync**: nudge by seconds if matches open a little early or late.
- **Not this event**: remove a wrong video.

## Files
- `.env` holds the FTC Events API key. It is private and not committed to git.
- `snackscout.db` holds your scouting notes. Back this up and share it between laptops.
- `cache/` stores API and YouTube lookups so the app keeps working on bad venue Wi-Fi.
- `clips/` stores downloaded match clips.

Optional `.env` settings: `OUR_TEAM_NUMBER=xxxxx` (adds a quick link on the home page), `FTC_SEASON=2026`, `CLIP_MAX_HEIGHT=480`.
