"""SnackScout - FTC alliance partner scouting for team Snack Time.

Run:  .venv\\Scripts\\python app.py   then open http://localhost:5000
"""
import hmac
import json
import re
import time
from datetime import date, timedelta

from functools import wraps

from flask import (Flask, Response, abort, g, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)

from snackscout import (analysis, autosync, clips, cloud, db, ftcevents, ftcscout, google_auth, hub, report, slack_bot,
                        strategy, themes, version, video)
from snackscout.config import (ANALYSIS_DIR, CLIPS_DIR, HOST, LOCAL_NO_PASSWORD, OUR_TEAM, PORT, SEASON,
                               TEAM_PASSWORD, secret_key)
from snackscout.config import env_set as config_env_set
from snackscout.ftcscout import ApiError

app = Flask(__name__)
app.config.update(OUR_TEAM=OUR_TEAM, SECRET_KEY=secret_key(), PERMANENT_SESSION_LIFETIME=timedelta(days=60),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
db.init()
cloud.start()
slack_bot.boot()

CLIP_RE = re.compile(r"[A-Za-z0-9_-]+\.mp4")
VIDEO_RE = re.compile(r"[A-Za-z0-9_-]{11}")
EVENT_RE = re.compile(r"[A-Za-z0-9]{2,20}")


def check(pattern, value):
    """Reject anything that isn't a plain clip/video/event id (no paths)."""
    if not isinstance(value, str) or not pattern.fullmatch(value):
        abort(400)
    return value


# ---------------- accounts ----------------

PUBLIC_ENDPOINTS = {"login", "signup", "setup", "static", "public_status", "google_start", "google_callback"}


def is_local_user():
    """Someone sitting at this laptop (not via the Cloudflare tunnel, a proxy, or the Wi-Fi)."""
    if not LOCAL_NO_PASSWORD:
        return False
    proxied = request.headers.get("Cf-Connecting-Ip") or request.headers.get("X-Forwarded-For")
    return request.remote_addr in ("127.0.0.1", "::1") and not proxied


def team_code():
    return db.team_config("team_code") or TEAM_PASSWORD


def safe_next(default="/"):
    nxt = request.args.get("next") or default
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def log_in(user):
    session.clear()
    session.permanent = True
    session["user"] = user["username"]


@app.before_request
def require_login():
    g.user = None
    if session.get("user"):
        g.user = db.get_user(session["user"])
        if not g.user:  # account removed
            session.clear()
    db.set_actor(g.user["username"] if g.user else None)
    if g.user or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Log in first."), 401
    if db.user_count() == 0:
        return redirect(url_for("setup"))
    return redirect(url_for("login", next=request.full_path if request.query_string else request.path))


def admin_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if not g.user or g.user["role"] != "admin":
            abort(403)
        return fn(*a, **kw)
    return inner


USERNAME_RE = re.compile(r"[a-z0-9_.-]{3,24}")


def _validate_new_account(f):
    u = db.norm_username(f.get("username"))
    if not USERNAME_RE.fullmatch(u):
        return "Usernames are 3-24 letters, numbers, dots, dashes or underscores."
    if len(f.get("password") or "") < 6:
        return "Passwords need at least 6 characters."
    if f.get("password") != f.get("password2"):
        return "The two passwords don't match."
    if db.get_user(u):
        return "That username is taken."
    return None


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Create the first (admin) account."""
    if db.user_count() > 0:
        return redirect(url_for("login"))
    local, code = is_local_user(), team_code()
    error = None
    if request.method == "POST":
        f = request.form
        error = _validate_new_account(f)
        if not error and not local and not (code and hmac.compare_digest(f.get("code", "").encode(), code.encode())):
            time.sleep(1)
            error = "Wrong team code. (Or set SnackScout up from the team laptop itself.)"
        new_code = (f.get("new_code") or "").strip()
        if not error and new_code and (len(new_code) < 6 or " " in new_code):
            error = "The team code needs 6+ characters and no spaces."
        if not error:
            if new_code:
                db.set_team_config("team_code", new_code)
            pending = session.get("g_pending")
            user = db.create_user(f["username"], f.get("display_name") or f["username"], f["password"], role="admin")
            if pending:
                db.link_google(user["username"], pending["sub"], pending["email"])
            log_in(user)
            return redirect(url_for("settings", welcome=1))
    return render_template("setup.html", error=error, local=local, code=code)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if db.user_count() == 0:
        return redirect(url_for("setup"))
    error = None
    if request.method == "POST":
        f = request.form
        code = team_code()
        pending = session.get("g_pending")
        if not code or not hmac.compare_digest(f.get("code", "").strip().encode(), code.encode()):
            time.sleep(1)  # slow down guessing
            error = "That team code isn't right. Ask your team lead for it."
        elif pending:
            # Google sign-up: the team code is all that's needed. No password; they log in with Google.
            if db.user_by_google(pending["sub"]):
                error = "That Google account already has an account. Use Sign in with Google."
            else:
                name = (f.get("display_name") or pending.get("name") or pending["email"]).strip()[:40]
                user = db.create_user(db.free_username(pending["email"]), name, None)
                db.link_google(user["username"], pending["sub"], pending["email"])
                log_in(user)
                return redirect(url_for("index", welcome=1))
        else:
            error = _validate_new_account(f)
        if not error:
            user = db.create_user(f["username"], f.get("display_name") or f["username"], f["password"])
            log_in(user)
            return redirect(safe_next())
    return render_template("signup.html", error=error, google=session.get("g_pending"),
                           google_on=google_auth.configured())


@app.route("/login", methods=["GET", "POST"])
def login():
    if db.user_count() == 0:
        return redirect(url_for("setup"))
    error = None
    if request.method == "POST":
        user = db.check_login(request.form.get("username"), request.form.get("password"))
        if user:
            log_in(user)
            return redirect(safe_next())
        time.sleep(1)  # slow down password guessing
        error = "Wrong username or password."
    return render_template("login.html", error=error or request.args.get("msg"),
                           google_on=google_auth.configured() and bool(google_auth.origin_for(request)))


@app.get("/auth/google/start")
def google_start():
    mode = request.args.get("mode", "login")
    if mode not in ("login", "link"):
        abort(400)
    if not google_auth.configured():
        return redirect(url_for("login", msg="Google sign-in isn't set up yet. Ask an admin (Settings → Team)."))
    if request.host.startswith("127.0.0.1"):  # Google only knows "localhost"
        return redirect(google_auth.LOCAL_ORIGIN + request.full_path)
    origin = google_auth.origin_for(request)
    if not origin:
        return render_template("error.html", message="Google sign-in works on the team laptop and through the online "
                               "link, but not on the same-Wi-Fi link. Log in with your username and password here."), 400
    if mode == "link" and not g.user:
        return redirect(url_for("login"))
    session["g_next"] = safe_next() if mode == "login" else url_for("settings", tab="account")
    return redirect(google_auth.start(app.secret_key, origin, mode, session))


@app.get("/auth/google/callback")
def google_callback():
    origin = google_auth.origin_for(request)
    try:
        if not origin:
            raise google_auth.GoogleError("Google sign-in can't finish on this address.")
        who = google_auth.finish(app.secret_key, origin, request.args, session)
    except google_auth.GoogleError as e:
        dest = "settings" if g.user else "login"
        return redirect(url_for(dest, tab="account", msg=str(e), bad=1) if g.user else url_for("login", msg=str(e)))
    nxt = session.pop("g_next", "/")
    if who["mode"] == "link":
        if not g.user:
            return redirect(url_for("login"))
        try:
            db.link_google(g.user["username"], who["sub"], who["email"])
        except ValueError as e:
            return redirect(url_for("settings", tab="account", msg=str(e), bad=1))
        return redirect(url_for("settings", tab="account", msg=f"Linked {who['email']}. You can now sign in with Google."))
    user = db.user_by_google(who["sub"])
    if user:
        log_in(user)
        return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
    # Not linked to anyone yet: sign up (team code + username + password), then it gets linked.
    session["g_pending"] = {"sub": who["sub"], "email": who["email"], "name": who["name"]}
    if db.user_count() == 0:
        return redirect(url_for("setup"))
    return redirect(url_for("signup"))


@app.post("/settings/account/unlink-google")
def unlink_google():
    if not g.user.get("pw_hash"):
        return redirect(url_for("settings", tab="account", bad=1,
                                msg="Set a password first. Otherwise you'd have no way to log in."))
    db.link_google(g.user["username"], None, None)
    return redirect(url_for("settings", tab="account", msg="Google account unlinked. Use your username and password to log in."))


@app.post("/settings/google")
@admin_required
def settings_google():
    cid, secret = (request.form.get("client_id") or "").strip(), (request.form.get("client_secret") or "").strip()
    if request.form.get("action") == "remove":
        db.set_team_config("google_client_id", "")
        db.set_team_config("google_client_secret", "")
        return redirect(url_for("settings", tab="team", msg="Google sign-in turned off."))
    if not cid.endswith(".apps.googleusercontent.com") or len(secret) < 10:
        return redirect(url_for("settings", tab="team", msg="That doesn't look like a Google Client ID and secret.", bad=1))
    db.set_team_config("google_client_id", cid)
    db.set_team_config("google_client_secret", secret)
    return redirect(url_for("settings", tab="team", msg="Google sign-in is on for every laptop (shared through the team cloud)."))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.context_processor
def inject_user():
    prefs = db.get_prefs(g.user["username"]) if getattr(g, "user", None) else {}
    return dict(current_user=getattr(g, "user", None), prefs=prefs, theme_css=themes.css(prefs),
                app_version=version.display(version.RUNNING), current_event=_current_event_code() if prefs is not None and getattr(g, "user", None) else None)


def _current_event_code():
    """Our team's competition happening today (for quick actions), from the cached team report."""
    if not str(OUR_TEAM).isdigit():
        return None
    try:
        r = report.build(int(OUR_TEAM))
    except Exception:  # noqa: BLE001 - never break a page over this
        return None
    today = date.today().isoformat()
    return next((e["event"]["code"] for e in (r or {}).get("events", []) if e["event"]["start"] <= today <= e["event"]["end"]), None)


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.template_filter("num")
def num(v, digits=1):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return v


@app.template_filter("timestamp")
def timestamp(v):
    from datetime import datetime
    return datetime.fromtimestamp(v).strftime("%b %d, %I:%M %p").replace(" 0", " ")


@app.template_filter("pct")
def pct(v):
    return "–" if v is None else f"{v}%"


@app.errorhandler(ApiError)
def api_error(e):
    return render_template("error.html", message=str(e)), 502


@app.route("/")
def index():
    """Home dashboard: our next competition, plus favorites/recent teams (kept in the browser)."""
    today = date.today().isoformat()
    next_ev, our = None, None
    if OUR_TEAM:
        try:
            r = report.build(int(OUR_TEAM))
        except ApiError:
            r = None
        if r:
            our = r
            evs = sorted((e["event"] for e in r["events"]), key=lambda e: e["start"])
            next_ev = next((e for e in evs if e["start"] <= today <= e["end"]), None) or \
                next((e for e in evs if e["start"] > today), None)
            if next_ev:
                days = (date.fromisoformat(next_ev["start"]) - date.today()).days
                next_ev = dict(next_ev, days=days)
    return render_template("index.html", our_team=OUR_TEAM, season=SEASON, next_ev=next_ev, our=our)


@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect(url_for("index"))
    nums = re.findall(r"\d+", q)
    if len(nums) > 1 and re.fullmatch(r"[\d\s,]+", q):  # "16750, 3231" -> compare
        return redirect(url_for("compare", teams=",".join(nums)))
    if q.isdigit():
        return redirect(url_for("team", number=int(q)))
    events = ftcevents.search_events(q)
    exact = [e for e in events if e["code"].upper() == q.upper().replace(" ", "")]
    if exact:  # typed an event code like USMISCM3
        return redirect(url_for("event", code=exact[0]["code"]))
    try:
        results = ftcscout.search_teams(q)
    except ApiError:
        results = []
    if len(results) == 1 and not events:
        return redirect(url_for("team", number=results[0]["number"]))
    today = date.today().isoformat()
    # soonest-first for upcoming events, then most recent past ones
    events.sort(key=lambda e: (e["dateStart"][:10] < today, abs((date.fromisoformat(e["dateStart"][:10]) - date.today()).days)))
    return render_template("search.html", q=q, results=results, events=events[:40], today=today)


@app.route("/team/<int:number>")
def team(number):
    r = report.build(number, refresh=bool(request.args.get("refresh")))
    if not r:
        return render_template("error.html", message=f"Team {number} not found on FTCScout."), 404
    return render_template("team.html", r=r, number=number, season=SEASON)


@app.route("/events")
def events():
    day = request.args.get("date") or date.today().isoformat()
    todays = ftcscout.events_on(day)
    ours = []
    if OUR_TEAM:
        r = report.build(int(OUR_TEAM))
        ours = [e["event"] for e in (r["events"] if r else [])]
        ours.sort(key=lambda e: e["start"])
    our_codes = {e["code"] for e in ours}
    todays.sort(key=lambda e: (e["code"] not in our_codes, e["location"]["country"] != "USA", e["name"]))
    d = date.fromisoformat(day)
    return render_template("events.html", day=day, todays=todays, ours=ours, our_codes=our_codes,
                           today=date.today().isoformat(), our_team=OUR_TEAM,
                           prev_day=(d - timedelta(days=1)).isoformat(), next_day=(d + timedelta(days=1)).isoformat())


@app.get("/api/our-latest-result")
def our_latest_result():
    """Our most recent finished match (for the win/loss animation). Live from the event when we're competing today."""
    our = int(OUR_TEAM) if str(OUR_TEAM).isdigit() else None
    if not our:
        return jsonify(result=None)
    try:
        r = report.build(our)
    except ApiError:
        return jsonify(result=None)
    if not r:
        return jsonify(result=None)
    today = date.today().isoformat()
    cur = next((e["event"] for e in r["events"] if e["event"]["start"] <= today <= e["event"]["end"]), None)
    if cur:
        played = [m for m in strategy.event_view(cur["code"], our)["matches"] if m["played"]]
        if played:
            m = played[-1]
            return jsonify(result=dict(key=f"{cur['code']}:{m['description']}", result=m["played"]["result"], us=m["played"]["us"],
                                       them=m["played"]["them"], match=m["description"], event=cur["name"], recent=True))
    rows = sorted((m for e in r["events"] for m in e["matches"] if m["has_scores"]), key=lambda m: m["start_ts"] or 0)
    if not rows:
        return jsonify(result=None)
    m = rows[-1]
    ev_name = next((e["event"]["name"] for e in r["events"] if e["event"]["code"] == m["event"]), m["event"])
    return jsonify(result=dict(key=f"{m['event']}:{m['label']}", result=m["result"], us=m["score"], them=m["opp_score"],
                               match=m["label"], event=ev_name, recent=bool(m["start_ts"] and time.time() - m["start_ts"] < 36 * 3600)))


_hub_cache = {}


def get_hub(code, our, refresh=False):
    """Competition hub data, cached for 30 s so the match window and the page don't rebuild it twice."""
    key = (code, our)
    hit = _hub_cache.get(key)
    if hit and not refresh and time.time() - hit[0] < 30:
        return hit[1]
    h = hub.event_hub(code, our, refresh=refresh)
    _hub_cache[key] = (time.time(), h)
    return h


@app.route("/event/<code>")
def event(code):
    code = check(EVENT_RE, code.upper())
    our = int(request.args.get("team") or OUR_TEAM or 0)
    v = get_hub(code, our, refresh=bool(request.args.get("refresh")))
    if not v["event"] and not v["teams"]:
        return render_template("error.html", message=f"Event {code} not found."), 404
    return render_template("event.html", v=v, our=our, today=date.today().isoformat(),
                           picklist=_picklist(code), mnotes=_match_debriefs(code),
                           team_by={p["number"]: p for p in v["teams"]})


def _picklist(code):
    try:
        return json.loads(db.team_config(f"picklist:{code}") or "{}")
    except ValueError:
        return {}


def _match_debriefs(code):
    with db.conn() as c:
        rows = c.execute("SELECT key, value FROM team_config WHERE key LIKE ?", (f"mnote:{code}:%",)).fetchall()
    return {r["key"].split(":", 2)[2]: r["value"] for r in rows if r["value"]}


@app.get("/api/event/<code>/match/<key>")
def api_match(code, key):
    """Everything the scout-a-match window needs: teams, prediction/result, everyone's notes for this match."""
    code, our = check(EVENT_RE, code.upper()), int(request.args.get("team") or OUR_TEAM or 0)
    h = get_hub(code, our)
    m = hub.find_match(h, key)
    if not m:
        abort(404)
    profs = {p["number"]: p for p in h["teams"]}
    teams = []
    for side in ("red", "blue"):
        for n in m[side]:
            note = db.match_notes(n).get((code, m["match_id"])) or {}
            p = profs.get(n, {})
            teams.append(dict(number=n, name=p.get("name"), alliance=side, opr=p.get("opr"), ours=n == our,
                              note={k: note.get(k) for k in db.MATCH_FIELDS} | {"by": note.get("updated_by")} if note else None))
    return jsonify(match=m, teams=teams, event=dict(code=code, name=(h["event"] or {}).get("name")),
                   debrief=db.team_config(f"mnote:{code}:{key}") or "",
                   me=g.user["display_name"])


@app.get("/api/event/<code>/match/<key>/video")
def api_match_video(code, key):
    code, our = check(EVENT_RE, code.upper()), int(request.args.get("team") or OUR_TEAM or 0)
    h = get_hub(code, our)
    m = hub.find_match(h, key)
    ev = h["event"]
    if not m or not ev or not m["start_ts"]:
        return jsonify(video=None, reason="This match hasn't been played yet." if m and not m["played"] else "No start time for this match.")
    starts = [x["start_ts"] for x in h["matches_all"] if x["start_ts"]]
    vids = video.ensure_event_videos(ev, starts)
    loc = video.locate(vids, m["label"], m["start_ts"], field=m.get("field"))
    if not loc:
        return jsonify(video=None, reason="No livestream found for this event. Add one under Video settings on a team page.")
    loc["clip_name"] = clips.clip_name(code, m["label"], loc["video_id"], loc["start"])
    loc["clip"] = clips.status(loc["clip_name"])
    return jsonify(video=loc)


@app.post("/api/event/<code>/match/<key>/debrief")
def api_match_debrief(code, key):
    code = check(EVENT_RE, code.upper())
    check(re.compile(r"[A-Z]{1,2}-[0-9-]{1,9}"), key)
    text = ((request.get_json() or {}).get("text") or "").strip()[:4000]
    db.set_team_config(f"mnote:{code}:{key}", text)
    return jsonify(ok=True)


@app.route("/api/event/<code>/picklist", methods=["GET", "POST"])
def api_picklist(code):
    code = check(EVENT_RE, code.upper())
    if request.method == "POST":
        d = request.get_json() or {}
        order = [int(n) for n in d.get("order", []) if str(n).isdigit()][:60]
        status = {str(int(k)): v for k, v in (d.get("status") or {}).items()
                  if str(k).isdigit() and v in ("picked", "declined", "dnp", "")}
        db.set_team_config(f"picklist:{code}", json.dumps({"order": order, "status": status, "by": g.user["display_name"]}))
    return jsonify(_picklist(code))


@app.route("/compare")
def compare():
    nums = [int(n) for n in re.findall(r"\d+", request.args.get("teams", ""))][:6]
    reports = [(n, report.build(n)) for n in nums]
    return render_template("compare.html", reports=reports, teams=",".join(map(str, nums)))


@app.post("/team/<int:number>/notes")
def team_notes(number):
    db.save_team_note(number, request.form)
    return redirect(url_for("team", number=number, saved=1) + "#pit")


# ---------------- JSON API used by the page ----------------

@app.post("/api/match-note")
def match_note():
    d = request.get_json()
    vals = {k: d.get(k) for k in db.MATCH_FIELDS}
    for k in ("auto_pollen", "teleop_pollen", "nectar", "hive_tips", "missed", "rating"):
        vals[k] = int(vals[k]) if str(vals.get(k) or "").strip().lstrip("-").isdigit() else None
    for k in ("defense", "broke_down"):
        vals[k] = 1 if vals.get(k) else 0
    if not (vals.get("scouter") or "").strip():
        vals["scouter"] = g.user["display_name"]
    db.save_match_note(int(d["team"]), d["event"], int(d["match_id"]), d.get("label"), vals)
    return jsonify(ok=True)


@app.get("/api/videos/<int:number>")
def videos(number):
    """Slow part (YouTube lookups) - the page calls this after it loads."""
    refresh = bool(request.args.get("refresh"))
    r = report.build(number)
    if not r:
        abort(404)
    matches, events = {}, {}
    for ev in r["events"]:
        times = [m["start_ts"] for m in ev["matches"] if m["start_ts"]]
        if not times:
            continue
        vids = video.ensure_event_videos(ev["event"], times, refresh=refresh)
        events[ev["event"]["code"]] = vids
        fields = {}
        if len(vids) > 1:  # several streams: match each match to its field's stream
            fields = {hub.match_key(s["tournamentLevel"], s.get("series"), s["matchNumber"]): s.get("field")
                      for s in ftcevents.schedule(ev["event"]["code"])}
        for m in ev["matches"]:
            loc = video.locate(vids, m["label"], m["start_ts"], field=fields.get(m["label"]))
            if loc:
                loc["clip_name"] = clips.clip_name(m["event"], m["label"], loc["video_id"], loc["start"])
                loc["clip"] = clips.status(loc["clip_name"])
                matches[f"{m['event']}:{m['id']}"] = loc
    return jsonify(matches=matches, events=events,
                   team_videos=video.team_videos(number, r["team"]["name"]))


@app.post("/api/event-video")
def add_event_video():
    d = request.get_json()
    vid = video.video_id_from_url(d.get("url"))
    if not vid:
        return jsonify(ok=False, error="Couldn't find a YouTube video in that link."), 400
    meta = video.video_meta(vid, refresh=True)
    if not meta:
        return jsonify(ok=False, error="yt-dlp couldn't read that video."), 400
    if not meta.get("start_ts") and not meta.get("chapters"):
        return jsonify(ok=False, error="That video isn't a recorded livestream and has no chapters, "
                                       "so SnackScout can't line up match times with it."), 400
    db.add_event_video(check(EVENT_RE, d["event"]), meta, "manual")
    return jsonify(ok=True)


@app.post("/api/event-video/sync")
def sync_event_video():
    d = request.get_json()
    db.set_sync(check(EVENT_RE, d["event"]), check(VIDEO_RE, d["video_id"]), float(d["offset"]))
    return jsonify(ok=True)


@app.post("/api/event-video/hide")
def hide_event_video():
    d = request.get_json()
    db.hide_video(check(EVENT_RE, d["event"]), check(VIDEO_RE, d["video_id"]))
    return jsonify(ok=True)


@app.post("/api/clip")
def make_clip():
    d = request.get_json()
    check(re.compile(r"[A-Za-z0-9 -]{1,20}"), d["label"])
    return jsonify(clips.request(check(EVENT_RE, d["event"]), d["label"], check(VIDEO_RE, d["video_id"]), int(d["offset"])))


@app.get("/api/clip-status")
def clip_status():
    return jsonify({n: clips.status(check(CLIP_RE, n)) for n in request.args.getlist("name")})


@app.get("/clips/<path:name>")
def serve_clip(name):
    return send_from_directory(CLIPS_DIR, name)


# ---------------- OpenCV analysis ----------------

@app.get("/analysis/<path:name>")
def serve_analysis(name):
    return send_from_directory(ANALYSIS_DIR, name)


@app.get("/api/frame")
def frame():
    img = analysis.grab_frame(check(CLIP_RE, request.args.get("clip")), float(request.args.get("t", 60)))
    if img is None:
        abort(404)
    return Response(img, mimetype="image/jpeg")


@app.route("/api/calibration/<video_id>", methods=["GET", "POST"])
def calibration(video_id):
    check(VIDEO_RE, video_id)
    if request.method == "POST":
        d = request.get_json()
        db.save_calibration(video_id, [round(v) for v in d["red"]], [round(v) for v in d["blue"]])
    return jsonify(db.calibration(video_id))


@app.post("/api/analyze")
def analyze():
    d = request.get_json()
    check(CLIP_RE, d.get("clip")), check(VIDEO_RE, d.get("video_id"))
    if clips.status(d["clip"])["state"] != "done":
        return jsonify(state="error", error="Download the clip first."), 400
    if d.get("force"):
        db.clear_shot_labels(d["clip"])  # burst numbering changes on a re-run
    return jsonify(analysis.request(d["clip"], db.calibration(d["video_id"]), force=bool(d.get("force"))))


@app.get("/api/analysis")
def get_analysis():
    clip = check(CLIP_RE, request.args.get("clip"))
    out = analysis.result(clip)
    out["labels"] = db.shot_labels(clip, int(request.args["team"]))
    return jsonify(out)


@app.post("/api/shot-label")
def shot_label():
    d = request.get_json()
    db.save_shot_label(check(CLIP_RE, d.get("clip")), int(d["burst"]), int(d["team"]), d["event"], int(d["match_id"]),
                       int(d["n"]), d["phase"], d["label"])
    return jsonify(ok=True)


@app.post("/api/event-video/autosync")
def autosync_start():
    d = request.get_json()
    check(EVENT_RE, d.get("event")), check(VIDEO_RE, d.get("video_id"))
    ev = ftcscout.event(d["event"], refresh=True) or {}
    starts = [video.ts(m["actualStartTime"]) for m in ev.get("matches") or [] if m.get("actualStartTime")]
    if not starts:
        return jsonify(state="error", error="No played matches with official start times at this event yet."), 400
    return jsonify(autosync.request(d["event"], d["video_id"], starts))


@app.get("/api/event-video/autosync")
def autosync_status():
    return jsonify(autosync.status(request.args["event"], request.args["video_id"]))


@app.post("/api/event-video/fix-sync")
def fix_sync():
    """Apply the offset the scoreboard reader measured (match start seen early/late in the clip)."""
    d = request.get_json()
    db.shift_sync(check(EVENT_RE, d["event"]), check(VIDEO_RE, d["video_id"]), float(d["delta"]))
    return jsonify(ok=True)


# ---------------- settings ----------------

@app.route("/whats-new")
def whats_new():
    return render_template("whats_new.html", releases=version.changelog(), running=version.RUNNING,
                           installed=version.read(), display=version.display)


@app.route("/settings")
def settings():
    return render_template("settings.html", palettes=themes.PALETTES, users=db.list_users(),
                           code=team_code() if g.user["role"] == "admin" else None,
                           cloud_status=cloud.status(), admins=db.admin_count(),
                           google_on=google_auth.configured(), google_here=bool(google_auth.origin_for(request)),
                           google_client_id=google_auth.client()[0] if g.user["role"] == "admin" else None,
                           google_redirects=[google_auth.LOCAL_REDIRECT, google_auth.RELAY_URL],
                           slack=slack_bot.status(),
                           tab=request.args.get("tab", "look"), welcome=request.args.get("welcome"))


@app.post("/api/prefs")
def save_prefs():
    prefs = themes.clean(request.get_json() or {})
    db.save_prefs(g.user["username"], prefs)
    return jsonify(ok=True, prefs=prefs, css=themes.css(prefs))


@app.post("/settings/account")
def settings_account():
    f = request.form
    changes = {}
    name = (f.get("display_name") or "").strip()
    if name and name != g.user["display_name"]:
        changes["display_name"] = name[:40]
    if f.get("new_password"):
        has_pw = bool(g.user.get("pw_hash"))  # Google-only accounts set their first password without one
        if has_pw and not db.check_login(g.user["username"], f.get("current_password")):
            time.sleep(1)
            return redirect(url_for("settings", tab="account", msg="Your current password isn't right.", bad=1))
        if len(f["new_password"]) < 6 or f["new_password"] != f.get("new_password2"):
            return redirect(url_for("settings", tab="account", msg="New passwords must match and be 6+ characters.", bad=1))
        changes["password"] = f["new_password"]
    if changes:
        db.update_user(g.user["username"], **changes)
    return redirect(url_for("settings", tab="account", msg="Saved." if changes else "Nothing changed."))


@app.post("/settings/team/code")
@admin_required
def settings_team_code():
    code = (request.form.get("code") or "").strip()
    if len(code) < 6 or " " in code:
        return redirect(url_for("settings", tab="team", msg="The team code needs 6+ characters and no spaces.", bad=1))
    db.set_team_config("team_code", code)
    return redirect(url_for("settings", tab="team", msg="Team code changed. Existing accounts keep working."))


@app.post("/settings/team/user")
@admin_required
def settings_team_user():
    u, action = db.norm_username(request.form.get("username")), request.form.get("action")
    target = db.get_user(u)
    if not target:
        abort(404)
    is_last_admin = target["role"] == "admin" and db.admin_count() <= 1
    if action in ("make_member", "remove") and is_last_admin:
        return redirect(url_for("settings", tab="team", msg="The team needs at least one admin.", bad=1))
    if action == "make_admin":
        db.update_user(u, role="admin")
    elif action == "make_member":
        db.update_user(u, role="member")
    elif action == "remove":
        db.update_user(u, deleted=1)
    elif action == "reset":
        import secrets
        temp = "snack-" + secrets.token_hex(3)
        db.update_user(u, password=temp)
        return redirect(url_for("settings", tab="team", msg=f"Temporary password for {target['display_name']}: {temp}. "
                                                            "They can change it in Settings → Account."))
    return redirect(url_for("settings", tab="team", msg="Done."))


@app.post("/settings/cloud")
@admin_required
def settings_cloud():
    url, key = cloud.normalize_url(request.form.get("url")), (request.form.get("key") or "").strip()
    if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", url):
        return redirect(url_for("settings", tab="cloud", msg="The URL should look like https://abcd1234.supabase.co", bad=1))
    ok, msg = cloud.test(url, key)
    if not ok:
        return redirect(url_for("settings", tab="cloud", msg=msg, bad=1))
    cloud.configure(url, key)
    return redirect(url_for("settings", tab="cloud", msg="Connected! Your scouting will sync to the team cloud."))


@app.post("/settings/slack")
@admin_required
def settings_slack():
    f = request.form
    bot, app_tok, channel = (f.get("bot_token") or "").strip(), (f.get("app_token") or "").strip(), (f.get("channel") or "").strip()
    if not bot.startswith("xoxb-") or not app_tok.startswith("xapp-"):
        return redirect(url_for("settings", tab="slack", bad=1,
                                msg="The Bot token starts with xoxb- and the App-level token starts with xapp-."))
    st = slack_bot.configure(bot, app_tok, channel or "#scouting")
    if not st["connected"]:
        return redirect(url_for("settings", tab="slack", bad=1, msg=st["error"] or "Couldn't connect to Slack."))
    return redirect(url_for("settings", tab="slack", msg=f"Connected to {st['team']} as @{st['bot']}. Try /scout help in Slack."))


@app.post("/settings/slack/options")
@admin_required
def settings_slack_options():
    for k in ("remind", "results", "notes"):
        db.set_team_config("slack_" + k, "1" if request.form.get(k) else "0")
    ch = (request.form.get("channel") or "").strip()
    if ch and ch != slack_bot.status()["channel"]:
        config_env_set("SLACK_CHANNEL", ch)
        slack_bot._cfg["channel"] = ch
        slack_bot._channel_id = None
    return redirect(url_for("settings", tab="slack", msg="Saved."))


@app.post("/settings/slack/disconnect")
@admin_required
def settings_slack_disconnect():
    slack_bot.disconnect()
    return redirect(url_for("settings", tab="slack", msg="Slack disconnected from this laptop."))


@app.post("/api/slack/test")
@admin_required
def slack_test():
    try:
        slack_bot.send(f"👋 Hi from SnackScout {version.display(version.RUNNING)}! I'll post match reminders, results and new "
                       "scouting notes here. Try `/scout help`.")
        return jsonify(ok=True)
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=str(e)[:300])


@app.get("/api/slack/manifest")
@admin_required
def slack_manifest():
    return Response((version.ROOT / "slack" / "manifest.json").read_text(encoding="utf-8"), mimetype="text/plain")


@app.get("/api/schema.sql")
@admin_required
def schema_sql():
    return Response(cloud.SCHEMA_SQL.read_text(encoding="utf-8"), mimetype="text/plain")


@app.post("/api/cloud/sync")
def cloud_sync():
    return jsonify(cloud.sync_now())


@app.get("/api/cloud/status")
def cloud_status():
    s = cloud.status()
    s.pop("url", None)
    return jsonify(s)


@app.get("/api/public/status")
def public_status():
    """For the launcher on this laptop: no secrets, just whether setup is needed and cloud health."""
    s = cloud.status()
    sl = slack_bot.status()
    return jsonify(setup_needed=db.user_count() == 0, users=db.user_count(), version=version.RUNNING,
                   slack=dict(configured=sl["configured"], connected=sl["connected"]),
                   cloud=dict(configured=s["configured"], ok=s["ok"], ago=s["ago"], pending=s["pending"]))


if __name__ == "__main__":
    from waitress import serve
    print(f"SnackScout {version.display(version.RUNNING)} running - open http://localhost:{PORT}")
    serve(app, host=HOST, port=PORT, threads=12)
