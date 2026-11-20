# 🍿 SnackScout

Alliance-partner scouting for FTC team **34672 Snack Time** (2026-27 BIOBUZZ).

## Start it

Double-click **`SnackScout.bat`**. The first run sets everything up, then your browser opens http://localhost:5000.

Other devices on the same Wi-Fi can open `http://<this-laptop's-IP>:5000`.

Needs Python 3.11+ and ffmpeg on PATH. The other packages (yt-dlp, OpenCV) are installed automatically into `.venv`.

## Accounts

- **First time:** open SnackScout on the team laptop (the launcher's **Set up** button) and create the **admin** account.
  You also choose the **team code** there.
- **Teammates:** on the login page, click **Create an account** and enter the team code once. Everyone gets their own
  username and password, and their scouting is signed with their name.
- **Admins** (Settings → Team) can make other admins, reset someone's password (gives a temporary one), remove people,
  and change the team code. The team always keeps at least one admin.

## Team cloud (Supabase, free)

Without the cloud, scouting is saved on the laptop that runs SnackScout. With it, every laptop running SnackScout shares
the same accounts, notes, robot notes, video settings and shot reviews. Each laptop keeps working offline at venues, and
changes upload by themselves when it's back online. If two people edit the same thing, the newest edit wins.

One-time setup (about 5 minutes, admin only):
1. Go to **supabase.com**, sign up (free), and click **New project**. Name it `snackscout` and pick a region near you.
2. Open **SQL Editor → New query**, paste all of `supabase/schema.sql`, and click **Run**.
   (Settings → Team cloud has a **Copy the SQL** button.)
3. Open **Project Settings → API**. Copy the **Project URL** and the **service_role** secret key.
4. In SnackScout, open **Settings → Team cloud**, paste both values, and click **Test & connect**. Do the same on every
   other laptop that runs SnackScout.

The key is saved in `.env` on that laptop only. It is never sent to browsers or committed to git.
The cloud pill at the top of every page shows the status: **Synced**, **N to sync**, **Offline** or **Local only**.
Free Supabase projects pause after about a week with no activity; click **Restore** in the Supabase dashboard to wake one.

## Settings

Open **⚙️ Settings** from the avatar menu, or press `,`. Settings are saved per person:
- **Look & feel:** 8 color palettes or your own accent color, Auto / Light / Dark, corner roundness, spacing, text size,
  and animations (Full / Subtle / Off).
- **Scouting:** how often the event page auto-refreshes, and whether match tables show all columns.
- **Account:** your display name and password.

Shortcuts: `/` search · `t` dark/light · `,` settings · `Ctrl+Enter` saves a scouting form.

## The SnackScout launcher (recommended)

Open **SnackScout** from the Desktop or Start menu. To recreate the shortcuts, run
`powershell -ExecutionPolicy Bypass -File launcher\make_shortcuts.ps1`.

- **🌐 Go online** starts SnackScout and a free Cloudflare tunnel. Your team opens
  **https://kieran-snack.github.io/scout**. That link never changes, so print its QR code once and tape it in the pit.
- **Copy invite for team** copies the link and team code, ready to paste in your team chat.
- **Team code:** show it, copy it, or change it right there. The card above it shows accounts and the team cloud.
- **Same Wi-Fi link:** works at venues even when the internet is slow.
- **Keep laptop awake** while online. Keep the lid open and the laptop plugged in.
- **Closing the launcher** takes SnackScout offline. Visitors then see "SnackScout is offline" instead of an error.

The permanent link is a tiny GitHub Pages site (`kieran-snack/kieran-snack.github.io`). Each time you go online, the launcher
uses the GitHub CLI (`gh`, logged in as kieran-snack) to point it at the new tunnel. Link shorteners like is.gd refuse
Cloudflare tunnel links, which is why it works this way.

`SnackScout-Online.bat` still works as a no-frills fallback. It shows a link that changes every time.

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
