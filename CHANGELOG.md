# SnackScout changelog

Version numbers work like this:
- **Small updates** (fixes and polish) add a third number: 1.5 → 1.5.1 → 1.5.2
- **Bigger releases** (new features) bump the second number: 1.5 → 1.6 → 1.7

To release, run `.venv\Scripts\python release.py patch "what changed"` for a small update, or use `minor` for a bigger
release. It updates `VERSION` and adds the entry below. Then commit and tag (`git tag v1.5.1`).

## 1.8 (2026-11-20)
- Graphs on team pages: points per match (auto and teleop) and OPR at each event
- Graphs on competition pages: who scores the most (OPR of every team), score spread, and our scores next to the other alliance
- Graphs on Compare: points each team adds and how reliable they are
- Hover any bar or point for details. Graphs work offline and follow light and dark mode

## 1.7.1 (2026-11-20)
- Watch is now two buttons: Watch here (plays inside SnackScout) and YouTube ↗ (opens it on YouTube at the start of the match), for videos whose owners turned off playback on other websites

## 1.7 (2026-11-20)
- Competition hub: every match at an event (not just ours) with scores, predictions, upsets and a what-to-watch line
- Scout any match right from the competition page: video plus a form for each of the 4 robots, and match notes for the whole match
- Alliance selection: suggested partners with reasons, and a shared pick list you can reorder and mark during selection
- Live rankings and event highs: high score, best auto, biggest win, closest match, upsets
- Search competitions worldwide from the search bar (names, cities, event codes)
- Win/loss animations after our matches: swinging monkey, popcorn, confetti or rain, trophy or balloon, dancing or toppling robot
- Quick actions (Ctrl+K or the lightning button), home page shortcuts, and a How-to guide (Help in the top bar)
- Watch opens an in-app player that always starts at the match (YouTube's page could resume where you left off)
- Fixed: at two-field events videos could open the other field's stream; analysis could pick the previous match in a clip
- Slack result posts lead with the outcome (We won Q8, 68–44)
- Launcher renamed to SnackScout Launcher; the restart animation no longer makes the buttons jump

## 1.6 (2026-11-19)
- Slack: /scout command for team stats, our next match, today's schedule and comparisons
- Slack: automatic match reminders, results and new scouting notes in a team channel
- Settings → Slack with step-by-step setup and a ready-made Slack app manifest
- Launcher shows whether Slack is connected

## 1.5 (2026-11-19)
- Sign in with Google. New teammates join with Google and just the team code; their username comes from their email.
- Existing accounts can link or unlink Google under Settings → Account. Google-only accounts can add a password later.
- Google sign-in also works through the online link, via a relay page on kieran-snack.github.io.
- Privacy policy page for the Google app (kieran-snack.github.io/scout/privacy.html).
- Version numbers across SnackScout: shown in the app footer, a What's new page, and the launcher.
- Launcher: Restart button, and a warning when the running SnackScout is older than the installed files.
- Fixed: team cloud uploads failed with "Invalid path" when the Supabase URL ended in /rest/v1. SnackScout now cleans it up.
- Fixed: newer Supabase projects need an extra permission grant. It's now in supabase/schema.sql, and errors explain what to do.

## 1.4 (2026-11-19)
- Desktop launcher app with one-click Go online, a QR code, and a permanent link at kieran-snack.github.io/scout.
- Accounts: the first account becomes admin; teammates sign up with the team code.
- Team cloud on Supabase: everyone's scouting syncs across laptops, works offline, newest edit wins.
- Settings page: 8 color palettes or a custom color, dark mode, corners, spacing, text size and animations.
- Redesigned pages, summary tags on teams, favorites, recent teams, sortable tables, event countdown.
- New loading bar and loading circles that never visibly restart, plus hover and reveal animations.

## 1.3 (2026-11-19)
- SnackScout-Online.bat: share SnackScout from the laptop through a free Cloudflare tunnel.

## 1.2 (2026-11-12)
- Team password login and one-command Oracle Cloud setup.

## 1.1 (2026-11-12)
- OpenCV video analysis: scoreboard reading, pollen shot detection and auto-sync of livestreams.
- Competition picker, match predictions and strategy tips for team 34672.

## 1.0 (2026-11-12)
- First version: team reports from FTCScout and the FTC Events API, match videos found on YouTube, clip downloads and scouting notes.
