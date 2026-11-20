# SnackScout changelog

Version numbers work like this:
- **Small updates** (fixes and polish) add a third number: 1.5 → 1.5.1 → 1.5.2
- **Bigger releases** (new features) bump the second number: 1.5 → 1.6 → 1.7

To release, run `.venv\Scripts\python release.py patch "what changed"` for a small update, or use `minor` for a bigger
release. It updates `VERSION` and adds the entry below. Then commit and tag (`git tag v1.5.1`).

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
