"""Slack integration: the /scout slash command and automatic posts.

  /scout 16750              team summary          /scout next      our next match + strategy
  /scout technototes        search by name        /scout event     today's schedule and results
  /scout compare 34672 16750                      /scout help

Uses Slack's Socket Mode: SnackScout connects *out* to Slack, so no public web address is needed. Only the
laptop that has the Slack tokens in its .env connects, so posts aren't duplicated by other laptops.
Automatic posts (each can be turned off in Settings → Integrations):
  * match reminders ~15 minutes before each of our matches
  * results after each of our matches, compared with the prediction
  * new scouting notes and robot notes saved by teammates (from any laptop, via the team cloud)
"""
import logging
import re
import threading
import time
from datetime import date, datetime

from . import config, db, ftcscout, report, strategy

PERMA = "https://kieran-snack.github.io/scout"
REMIND_MINUTES = 15
log = logging.getLogger("snackscout.slack")

_cfg = {"bot": config.SLACK_BOT_TOKEN, "app": config.SLACK_APP_TOKEN, "channel": config.SLACK_CHANNEL}
_state = {"connected": False, "error": None, "team": None, "bot": None, "posts": 0, "last_post": None}
_handler = None
_client = None
_channel_id = None
_lock = threading.Lock()


# =================================================================== formatting helpers
def _link(path, label):
    return f"<{PERMA}#{path}|{label}>"


def _pct(v):
    return "–" if v is None else f"{v}%"


def _num(v, d=1):
    return "–" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v))


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2990]}}


def _context(text):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text[:2990]}]}


def _msg(text, blocks=None, public=True):
    return {"text": text, "blocks": blocks or [_section(text)], "response_type": "in_channel" if public else "ephemeral"}


def _ours():
    return int(config.OUR_TEAM) if str(config.OUR_TEAM).isdigit() else None


def _current_event(team):
    """Today's event for this team, else its next upcoming one."""
    r = report.build(team)
    if not r:
        return None
    today = date.today().isoformat()
    evs = sorted((e["event"] for e in r["events"]), key=lambda e: e["start"])
    return next((e for e in evs if e["start"] <= today <= e["end"]), None) or \
        next((e for e in evs if e["start"] > today), None)


def _who(profiles):
    return ", ".join(f"*{p['number']}* {p['name']} ({_num(p['opr'], 0) if p.get('opr') is not None else 'new'})"
                     for p in profiles) or "–"


def _time(m):
    return m["time"][11:16] if m.get("time") else ""


DIFF_EMOJI = {"easy": "🟢", "fav": "🟢", "even": "🟡", "hard": "🟠", "vhard": "🔴"}


# =================================================================== /scout answers (pure: easy to test)
HELP = ("*SnackScout* commands:\n"
        "• `/scout 16750` – a team's stats, strengths and our scouting notes\n"
        "• `/scout technototes` – find a team by name\n"
        "• `/scout next` – our next match: partners, opponents, prediction, strategy\n"
        "• `/scout event` – today's schedule and results for us\n"
        "• `/scout compare 34672 16750 3231` – side by side\n"
        "• `/scout help` – this list")


def answer(text: str) -> dict:
    words = (text or "").strip().split()
    if not words or words[0].lower() in ("help", "?"):
        return _msg(HELP, public=False)
    cmd = words[0].lower()
    try:
        if cmd.isdigit():
            return team_summary(int(cmd))
        if cmd == "next":
            return next_match(int(words[1]) if len(words) > 1 and words[1].isdigit() else _ours())
        if cmd == "event":
            return event_summary(words[1].upper() if len(words) > 1 else None)
        if cmd in ("compare", "vs"):
            nums = [int(w) for w in re.findall(r"\d+", " ".join(words[1:]))][:5]
            return compare(nums) if len(nums) >= 2 else _msg("Give me 2–5 team numbers, e.g. `/scout compare 34672 16750`.", public=False)
        found = ftcscout.search_teams(" ".join(words))
        if len(found) == 1:
            return team_summary(found[0]["number"])
        if not found:
            return _msg(f"No team matches “{' '.join(words)}”. Try the team number.", public=False)
        lines = "\n".join(f"• `{t['number']}` {t['name']} ({t['location']['city']}, {t['location']['state']})" for t in found[:8])
        return _msg(f"Which one? Use `/scout <number>`:\n{lines}", public=False)
    except ftcscout.ApiError as e:
        return _msg(f"⚠️ Couldn't reach FTCScout right now: {e}", public=False)


def team_summary(n: int) -> dict:
    r = report.build(n)
    if not r:
        return _msg(f"Team {n} wasn't found.", public=False)
    t, s, q, sc, tn = r["team"], r["season"] or {}, r["quick"], r["scouted"], r["team_note"] or {}
    head = f"*{t['number']} · {t['name']}*  ({t['location']['city']}, {t['location']['state']})"
    blocks = [_section(head)]
    if s:
        stats = (f"*OPR* {_num(q['tot']['value'])} (#{q['tot']['rank']} of {q['count']})  ·  *Auto* {_num(q['auto']['value'])}  ·  "
                 f"*Teleop* {_num(q['dc']['value'])}\n*Record* {s['wins']}-{s['losses']}-{s['ties']}  ·  *Leaves* {_pct(s['leave_rate'])}  ·  "
                 f"*Parks* {_pct(s['park_rate'])}  ·  *Penalties* {_num(s['avg_penalties'])}/match  ·  *Hive tips* {_num(s['avg_tips'])}/match") if q else ""
        blocks.append(_section(stats or "No OPR yet."))
    else:
        blocks.append(_section("No matches played yet this season."))
    tags = [f"{'✅' if k == 'good' else '⚠️' if k == 'bad' else '•'} {txt}" for txt, k in r["verdict"]]
    if tags:
        blocks.append(_section("  ".join(tags)))
    extra = []
    if sc:
        extra.append(f"📝 *Our scouts* ({sc['n']} matches): {_num(((sc['avg_auto_pollen'] or 0) + (sc['avg_teleop_pollen'] or 0)), 1)} pollen/match, "
                     f"accuracy {_pct(sc['accuracy'])}, broke down {sc['breakdowns']}×")
    if tn.get("elements") or tn.get("drivetrain") or tn.get("notes"):
        bits = [x for x in (tn.get("elements"), tn.get("drivetrain"), tn.get("shooter")) if x]
        extra.append(f"🔧 *Pit notes:* {' · '.join(bits)}" + (f"\n> {tn['notes'][:300]}" if tn.get("notes") else ""))
    notes = sorted((m for m in db.match_notes(n).values() if m.get("notes")), key=lambda m: -(m.get("updated") or 0))[:2]
    for m in notes:
        extra.append(f"💬 _{m['match_label']}_ ({m.get('scouter') or 'scout'}): {m['notes'][:200]}")
    if extra:
        blocks.append(_section("\n".join(extra)))
    blocks.append(_context(_link(f"/team/{n}", "Open full report in SnackScout")))
    return _msg(head.replace("*", ""), blocks)


def _match_lines(m, our):
    icon = "🔴" if m["alliance"] == "Red" else "🔵"
    lines = [f"{icon} *{m['description']}*  {_time(m)}{'  · field ' + str(m['field']) if m.get('field') else ''}",
             f"*With:* {_who(m['partners'])}", f"*Against:* {_who(m['opponents'])}"]
    if m.get("played"):
        p = m["played"]
        lines.append(f"*Result:* {'✅ Won' if p['result'] == 'W' else '❌ Lost' if p['result'] == 'L' else '➖ Tied'} "
                     f"{p['us']}–{p['them']}  (predicted {m['pred_us']}–{m['pred_them']})")
    else:
        lines.append(f"{DIFF_EMOJI.get(m['diff_class'], '')} *{m['difficulty']}*: predicted {m['pred_us']}–{m['pred_them']} ({m['p_win']}% win)")
    return lines


def next_match(team) -> dict:
    if not team:
        return _msg("Set OUR_TEAM_NUMBER in SnackScout first, or use `/scout next 34672`.", public=False)
    ev = _current_event(team)
    if not ev:
        return _msg(f"Team {team} has no current or upcoming events.", public=False)
    v = strategy.event_view(ev["code"], team)
    if not v["schedule_out"]:
        return _msg(f"*{ev['name']}* ({ev['start']}): the match schedule isn't posted yet. Try again later.")
    m = v["next"]
    if not m:
        return _msg(f"*{ev['name']}*: no more matches for {team}. 🎉")
    blocks = [_section(f"⏭️ *Next match for {team}* at {ev['name']}"), _section("\n".join(_match_lines(m, team)))]
    if m["tips"]:
        blocks.append(_section("💡 *Strategy*\n" + "\n".join(f"• {t}" for t in m["tips"][:4])))
    blocks.append(_context(_link(f"/event/{ev['code']}", "Open event day in SnackScout")))
    return _msg(f"Next match: {m['description']}", blocks)


def event_summary(code=None) -> dict:
    team = _ours()
    if not code:
        ev = _current_event(team) if team else None
        if not ev:
            return _msg("No current event. Use `/scout event USMISCM3`.", public=False)
        code, name = ev["code"], ev["name"]
    else:
        name = code
    v = strategy.event_view(code, team or 0)
    if v["event"]:
        name = v["event"]["name"]
    if not v["schedule_out"]:
        return _msg(f"*{name}*: the match schedule isn't posted yet.")
    if not v["matches"]:
        return _msg(f"*{name}*: team {team} isn't in the schedule.")
    lines = []
    for m in v["matches"]:
        icon = "🔴" if m["alliance"] == "Red" else "🔵"
        mates = "+".join(str(p["number"]) for p in m["partners"]) or "–"
        opp = " & ".join(str(p["number"]) for p in m["opponents"])
        if m.get("played"):
            p = m["played"]
            res = f"{'✅' if p['result'] == 'W' else '❌' if p['result'] == 'L' else '➖'} {p['us']}–{p['them']}"
        else:
            res = f"{DIFF_EMOJI.get(m['diff_class'], '')} {m['difficulty']} ({m['p_win']}%)"
        lines.append(f"{icon} `{m['description'].replace('Qualification ', 'Q')}` {_time(m)} · with {mates} vs {opp} · {res}")
    played = [m for m in v["matches"] if m.get("played")]
    wins = sum(1 for m in played if m["played"]["result"] == "W")
    head = f"📅 *{name}* · {team}: {len(v['matches'])} matches" + (f", {wins}-{len(played) - wins} so far" if played else "")
    return _msg(head, [_section(head), _section("\n".join(lines)), _context(_link(f"/event/{code}", "Open event day in SnackScout"))])


def compare(nums) -> dict:
    rows = []
    for n in nums:
        r = report.build(n)
        if not r:
            rows.append(f"*{n}*: not found")
            continue
        q, s = r["quick"], r["season"] or {}
        rows.append(f"*{n}* {r['team']['name']}: OPR *{_num(q['tot']['value']) if q else '–'}* · auto {_num(q['auto']['value']) if q else '–'} · "
                    f"record {s.get('wins', 0)}-{s.get('losses', 0)}-{s.get('ties', 0)} · parks {_pct(s.get('park_rate'))} · "
                    f"penalties {_num(s.get('avg_penalties'))}")
    head = "⚖️ *Compare*"
    return _msg("Compare " + ", ".join(map(str, nums)),
                [_section(head), _section("\n".join(rows)), _context(_link(f"/compare?teams={','.join(map(str, nums))}", "Open in SnackScout"))])


# =================================================================== automatic posts
def _posted(key):
    return db.meta_get("slack:" + key) is not None


def _mark(key):
    db.meta_set("slack:" + key, str(time.time()))


def _on(name):
    return (db.team_config("slack_" + name) or "1") == "1"


def check_posts(post, now=None):
    """One pass of the automatic posts. `post(text, blocks)` sends a message. Returns how many were sent."""
    now = now or datetime.now()
    sent = 0
    team = _ours()
    if team and (_on("remind") or _on("results")):
        ev = _current_event(team)
        if ev and ev["start"] <= now.date().isoformat() <= ev["end"]:
            v = strategy.event_view(ev["code"], team)
            base_key = f"baseline:{ev['code']}"
            first_look = not _posted(base_key)
            for m in v["matches"]:
                key = f"{ev['code']}:{m['description']}"
                if m.get("played"):
                    if first_look:  # don't flood the channel with results from before Slack was connected
                        _mark("result:" + key)
                    elif _on("results") and not _posted("result:" + key):
                        p = m["played"]
                        word = "won" if p["result"] == "W" else "lost" if p["result"] == "L" else "tied"
                        icon = "🎉" if p["result"] == "W" else "😞" if p["result"] == "L" else "🤝"
                        headline = f"{icon} *We {word} {m['description']}, {p['us']}–{p['them']}*"
                        post(f"We {word} {m['description']}, {p['us']}–{p['them']}",
                             [_section(headline), _section("\n".join(_match_lines(m, team)))])
                        _mark("result:" + key)
                        sent += 1
                elif m.get("time") and _on("remind") and not _posted("remind:" + key):
                    start = datetime.fromisoformat(m["time"][:19])
                    mins = (start - now).total_seconds() / 60
                    if 0 <= mins <= REMIND_MINUTES:
                        blocks = [_section(f"⏰ *{m['description']} in {max(1, round(mins))} min*"),
                                  _section("\n".join(_match_lines(m, team)))]
                        if m["tips"]:
                            blocks.append(_section("💡 " + "\n💡 ".join(m["tips"][:3])))
                        post(f"{m['description']} in {round(mins)} minutes", blocks)
                        _mark("remind:" + key)
                        sent += 1
            if first_look:
                _mark(base_key)
    if _on("notes"):
        sent += _post_new_notes(post)
    return sent


def _post_new_notes(post):
    since = float(db.meta_get("slack:notes_since") or 0)
    if not since:  # first run: start from now, don't post the whole history
        db.meta_set("slack:notes_since", str(time.time()))
        return 0
    with db.conn() as c:
        mn = [dict(r) for r in c.execute("SELECT * FROM match_notes WHERE updated > ? ORDER BY updated", (since,))]
        tn = [dict(r) for r in c.execute("SELECT * FROM team_notes WHERE updated > ? ORDER BY updated", (since,))]
    if not mn and not tn:
        return 0
    latest = max([r["updated"] for r in mn + tn])
    lines = []
    for r in mn[:8]:
        counts = ", ".join(f"{v} {k}" for k, v in (("auto pollen", r.get("auto_pollen")), ("teleop pollen", r.get("teleop_pollen")),
                                                  ("nectar", r.get("nectar"))) if v)
        flags = " · broke down" if r.get("broke_down") else ""
        lines.append(f"📝 *{r['team']}* in {r.get('match_label') or 'a match'} by {r.get('scouter') or r.get('updated_by') or 'a scout'}"
                     f"{': ' + counts if counts else ''}{flags}" + (f"\n> {r['notes'][:200]}" if r.get("notes") else ""))
    for r in tn[:4]:
        bits = [x for x in (r.get("elements"), r.get("drivetrain"), r.get("shooter")) if x]
        lines.append(f"🔧 Robot notes for *{r['team']}* by {r.get('updated_by') or 'a scout'}" + (f": {' · '.join(bits)}" if bits else ""))
    more = len(mn) + len(tn) - len(lines)
    if more > 0:
        lines.append(f"…and {more} more.")
    post(f"{len(mn) + len(tn)} new scouting notes", [_section("\n".join(lines))])
    db.meta_set("slack:notes_since", str(latest))
    return 1


# =================================================================== connection
def configured():
    return bool(_cfg["bot"] and _cfg["app"])


def status():
    return dict(_state, configured=configured(), channel=_cfg["channel"],
                toggles={k: _on(k) for k in ("remind", "results", "notes")})


def _resolve_channel():
    global _channel_id
    ch = (_cfg["channel"] or "").strip()
    if not ch or not _client:
        return None
    if re.fullmatch(r"[CG][A-Z0-9]{6,}", ch):
        return ch
    if _channel_id:
        return _channel_id
    name, cursor = ch.lstrip("#").lower(), None
    while True:
        resp = _client.conversations_list(limit=500, cursor=cursor, exclude_archived=True, types="public_channel")
        for c in resp["channels"]:
            if c["name"] == name:
                _channel_id = c["id"]
                return _channel_id
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return None


def send(text, blocks=None):
    """Post to the team channel."""
    ch = _resolve_channel()
    if not ch:
        raise RuntimeError(f"Slack channel {_cfg['channel'] or '(none)'} wasn't found. Use a public channel name like #scouting.")
    _client.chat_postMessage(channel=ch, text=text, blocks=blocks, unfurl_links=False)
    _state["posts"] += 1
    _state["last_post"] = time.time()


def _poster_loop():
    while True:
        time.sleep(60)
        if not (_state["connected"] and _cfg["channel"]):
            continue
        try:
            check_posts(send)
        except Exception as e:  # noqa: BLE001 - never let posting crash SnackScout
            _state["error"] = f"Posting: {e}"[:300]
            log.warning("slack post failed: %s", e)


def start():
    """Connect to Slack if this laptop has tokens. Safe to call again after settings change."""
    global _handler, _client, _channel_id
    with _lock:
        if _handler:
            try:
                _handler.close()
            except Exception:  # noqa: BLE001
                pass
            _handler = None
        _state.update(connected=False, error=None)
        _channel_id = None
        if config.SLACK_DISABLED or not configured():
            return status()
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
            bolt = App(token=_cfg["bot"], logger=log)

            @bolt.command("/scout")
            def _scout(ack, command, respond):
                ack()
                try:
                    respond(**answer(command.get("text", "")))
                except Exception as e:  # noqa: BLE001
                    respond(text=f"⚠️ SnackScout hit an error: {e}", response_type="ephemeral")

            _client = bolt.client
            who = _client.auth_test()
            _handler = SocketModeHandler(bolt, _cfg["app"], logger=log)
            _handler.connect()
            _state.update(connected=True, team=who.get("team"), bot=who.get("user"))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "invalid_auth" in msg or "not_authed" in msg:
                msg = "Slack rejected the Bot token (xoxb-…). Copy it again from OAuth & Permissions."
            elif "xapp" in msg or "connections" in msg or "app_token" in msg.lower():
                msg = "Slack rejected the App-level token (xapp-…). It needs the connections:write scope."
            _state.update(connected=False, error=msg[:300])
    return status()


def configure(bot_token, app_token, channel):
    config.env_set("SLACK_BOT_TOKEN", bot_token.strip())
    config.env_set("SLACK_APP_TOKEN", app_token.strip())
    config.env_set("SLACK_CHANNEL", channel.strip())
    _cfg.update(bot=bot_token.strip(), app=app_token.strip(), channel=channel.strip())
    return start()


def disconnect():
    for k in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        config.env_set(k, "")
    _cfg.update(bot="", app="")
    return start()


_poster_started = False


def boot():
    """Called once when SnackScout starts."""
    global _poster_started
    if not _poster_started:
        _poster_started = True
        threading.Thread(target=_poster_loop, daemon=True, name="slack-posts").start()
    threading.Thread(target=start, daemon=True, name="slack-connect").start()
