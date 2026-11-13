"""SnackScout - FTC alliance partner scouting for team Snack Time.

Run:  .venv\\Scripts\\python app.py   then open http://localhost:5000
"""
import re

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

from snackscout import clips, db, ftcscout, report, video
from snackscout.config import CLIPS_DIR, OUR_TEAM, SEASON
from snackscout.ftcscout import ApiError

app = Flask(__name__)
db.init()


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
    db.add_event_video(d["event"], meta, "manual")
    return jsonify(ok=True)


@app.post("/api/event-video/sync")
def sync_event_video():
    d = request.get_json()
    db.set_sync(d["event"], d["video_id"], float(d["offset"]))
    return jsonify(ok=True)


@app.post("/api/event-video/hide")
def hide_event_video():
    d = request.get_json()
    db.hide_video(d["event"], d["video_id"])
    return jsonify(ok=True)


@app.post("/api/clip")
def make_clip():
    d = request.get_json()
    return jsonify(clips.request(d["event"], d["label"], d["video_id"], int(d["offset"])))


@app.get("/api/clip-status")
def clip_status():
    return jsonify({n: clips.status(n) for n in request.args.getlist("name")})


@app.get("/clips/<path:name>")
def serve_clip(name):
    return send_from_directory(CLIPS_DIR, name)


if __name__ == "__main__":
    print("SnackScout running - open http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
