"""SnackScout - FTC alliance partner scouting for team Snack Time.

Run:  .venv\\Scripts\\python app.py   then open http://localhost:5000
"""
import hmac
import re
import time
from datetime import date, timedelta

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)

from snackscout import analysis, autosync, clips, db, ftcscout, report, strategy, video
from snackscout.config import (ANALYSIS_DIR, CLIPS_DIR, HOST, LOCAL_NO_PASSWORD, OUR_TEAM, PORT, SEASON,
                               TEAM_PASSWORD, secret_key)
from snackscout.ftcscout import ApiError

app = Flask(__name__)
app.config.update(OUR_TEAM=OUR_TEAM, SECRET_KEY=secret_key(), PERMANENT_SESSION_LIFETIME=timedelta(days=60),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
db.init()

CLIP_RE = re.compile(r"[A-Za-z0-9_-]+\.mp4")
VIDEO_RE = re.compile(r"[A-Za-z0-9_-]{11}")
EVENT_RE = re.compile(r"[A-Za-z0-9]{2,20}")


def check(pattern, value):
    """Reject anything that isn't a plain clip/video/event id (no paths)."""
    if not isinstance(value, str) or not pattern.fullmatch(value):
        abort(400)
    return value


# ---------------- team password ----------------

def is_local_user():
    """Someone sitting at this laptop (not via the Cloudflare tunnel, a proxy, or the Wi-Fi)."""
    if not LOCAL_NO_PASSWORD:
        return False
    proxied = request.headers.get("Cf-Connecting-Ip") or request.headers.get("X-Forwarded-For")
    return request.remote_addr in ("127.0.0.1", "::1") and not proxied


@app.before_request
def require_login():
    if not TEAM_PASSWORD or session.get("ok") or is_local_user():
        return None
    if request.endpoint in ("login", "static"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Log in first."), 401
    return redirect(url_for("login", next=request.full_path if request.query_string else request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not TEAM_PASSWORD:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", "").encode(), TEAM_PASSWORD.encode()):
            session.permanent = True
            session["ok"] = True
            nxt = request.args.get("next") or "/"
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
        time.sleep(1)  # slow down password guessing
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.template_filter("num")
def num(v, digits=1):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return v


@app.template_filter("pct")
def pct(v):
    return "–" if v is None else f"{v}%"


@app.errorhandler(ApiError)
def api_error(e):
    return render_template("error.html", message=str(e)), 502


@app.route("/")
def index():
    return render_template("index.html", our_team=OUR_TEAM, season=SEASON)


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
    results = ftcscout.search_teams(q)
    if len(results) == 1:
        return redirect(url_for("team", number=results[0]["number"]))
    return render_template("search.html", q=q, results=results)


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
    return render_template("events.html", day=day, todays=todays, ours=ours, our_codes=our_codes,
                           today=date.today().isoformat(), our_team=OUR_TEAM)


@app.route("/event/<code>")
def event(code):
    our = int(request.args.get("team") or OUR_TEAM or 0)
    v = strategy.event_view(code.upper(), our, refresh=bool(request.args.get("refresh")))
    if not v["event"] and not v["teams"]:
        return render_template("error.html", message=f"Event {code} not found."), 404
    return render_template("event.html", v=v, our=our, today=date.today().isoformat())


@app.route("/compare")
def compare():
    nums = [int(n) for n in re.findall(r"\d+", request.args.get("teams", ""))][:6]
    reports = [(n, report.build(n)) for n in nums]
    return render_template("compare.html", reports=reports, teams=",".join(map(str, nums)))


@app.post("/team/<int:number>/notes")
def team_notes(number):
    db.save_team_note(number, request.form)
    return redirect(url_for("team", number=number) + "#pit")


# ---------------- JSON API used by the page ----------------

@app.post("/api/match-note")
def match_note():
    d = request.get_json()
    vals = {k: d.get(k) for k in db.MATCH_FIELDS}
    for k in ("auto_pollen", "teleop_pollen", "nectar", "hive_tips", "missed", "rating"):
        vals[k] = int(vals[k]) if str(vals.get(k) or "").strip().lstrip("-").isdigit() else None
    for k in ("defense", "broke_down"):
        vals[k] = 1 if vals.get(k) else 0
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
        for m in ev["matches"]:
            loc = video.locate(vids, m["label"], m["start_ts"])
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


if __name__ == "__main__":
    from waitress import serve
    print(f"SnackScout running - open http://localhost:{PORT}" + ("  (team password on)" if TEAM_PASSWORD else ""))
    serve(app, host=HOST, port=PORT, threads=12)
