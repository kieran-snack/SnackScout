# 🍿 SnackScout

Alliance-partner scouting for FTC team **34672 Snack Time** (2026-27 BIOBUZZ).

## Start it

Double-click **`SnackScout.bat`**. The first run sets everything up, then your browser opens http://localhost:5000.

Other devices on the same Wi-Fi can open `http://<this-laptop's-IP>:5000`.

Needs Python 3.11+ and ffmpeg on PATH. The other packages (yt-dlp, OpenCV) are installed automatically into `.venv`.

## Share it online (free, from this laptop)

Double-click **`SnackScout-Online.bat`**. It starts SnackScout plus a free Cloudflare tunnel. In the tunnel window,
find the `https://....trycloudflare.com` link and share it with the team, along with the `TEAM_PASSWORD` from `.env`.

- The link only works while the laptop is on and both windows are open.
- It **changes every time** you start it, so share the new one each time.
- On this laptop, `http://localhost:5000` works without the password.

## Competition day

1. Click **Competitions** and pick today's event. Our events are listed first.
2. Before the schedule is posted, the page lists every team at the event with their stats. It checks for the schedule every 2 minutes.
3. Once the schedule is up, each of our matches shows:
   - who we're **with** and **against**, with each team's season OPR;
   - a **predicted score and win %**, labeled Easy / Favorable / Toss-up / Hard / Very hard;
   - **strategy tips** drawn from the stats and our scouting notes: who should score, auto conflicts, partners who forget to leave or park, penalty-prone opponents, nectar threats, and which ranking points to chase;
   - the real result once it's played.

Predictions add up each robot's season OPR. Teams with no data count as 70% of the event median.

## Team reports

Type a team number or name.

| Section | Source |
|---|---|
| OPR, world rank, record, per-event rank | FTCScout |
| Each match: score, auto/teleop, hive tips, pollen+nectar in hive, garden, flower, penalties, RPs | FTCScout (official scores) |
| **This robot's** auto leave, auto park, endgame park | Official per-station scores |
| ▶ Jump to the match in the livestream | yt-dlp finds the event stream and lines it up with official match start times |
| ⬇ Match clip (watch offline) | yt-dlp + ffmpeg download just that 3-minute piece |
| 🔬 Video analysis | OpenCV (see below) |
| Pollen/nectar per robot, accuracy, defense, breakdowns | Your scouts, using the Scout form next to each clip |
| Side-by-side comparison | Type `34672, 16750` in the search box |

## OpenCV video analysis

Open **Scout** on a match, then click **Download clip & analyze**.

- **Scoreboard (automatic):** reads the official FIRST overlay twice a second, giving each alliance's score timeline, auto points, and the exact moments they scored (hive tips are +20). It also finds where the match really starts, so it can fix the video sync.
- **Pollen shots:** finds yellow pollen flying into each hive by color, motion, and tracking. The first time for each event stream, click **Mark hives** and drag a box around the red hive, then the blue one. The camera doesn't move, so every match from that stream reuses the boxes.
- **Whose shot?:** each burst of shots is shown as a picture with a yellow circle where the pollen was first seen. Tap **Ours / Partner / Not a shot**, which takes about 30 seconds per match. Confirmed shots feed the team's "Video analysis" stats and can fill in the scouting form.
- **🔍 Auto-sync:** if a stream's timing is off (the clip shows the wrong part of the stream), OpenCV reads the scoreboard straight from the YouTube stream, finds the matches, and lines them up with the official match times. It takes about 2 minutes once per stream.

Tested on real BIOBUZZ streams:
- The scoreboard reader matched every official final score it was tested on.
- Shot detection found exactly the 3 pollen the official data credits to blue in one match.
- Auto-sync fixed a stream that was 4 m 47 s off, to within 1 s, for all 5 of our matches.

Two limits: fully automatic per-robot tracking was unreliable (robots are small and collide a lot in the wide shot), which is why each shot burst gets one tap from a scout. And the shot detector counts pollen *flying into* the hive area, not confirmed scores.

### If a video is wrong or missing
Below each event's match table, open **"Livestreams used for this event"**:
- **Add stream**: paste the event's YouTube livestream (or a link like ftcwa.live that redirects to it).
- **🔍 Auto-sync** or **sync** (seconds): fix the timing.
- **Not this event**: remove a wrong video.

## Files
- `.env` holds the FTC Events API key and `OUR_TEAM_NUMBER=34672`. It is private and not committed (see `.env.example`).
- `snackscout.db` holds scouting notes, hive boxes, and shot labels. Back this up and share it between laptops.
- `cache/`, `clips/`, `analysis/` hold API/YouTube cache, downloaded clips, and video-analysis results.
