"""Turns raw API data into a scouting report for one team."""
from datetime import date

from . import db, ftcevents, ftcscout
from .video import ts


def _pct(xs):
    xs = [bool(x) for x in xs]
    return round(100 * sum(xs) / len(xs)) if xs else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _flower_counts(a: dict):
    pollen = nectar = 0
    for k in ("redAllianceFlowerState", "blueAllianceFlowerState", "scoringFlowerState", "audienceFlowerState"):
        for el in a.get(k) or []:
            if el == "Pollen":
                pollen += 1
            else:
                nectar += 1
    return pollen, nectar


LEVEL_ORDER = {"Quals": 0, "DoubleElim": 1, "Finals": 2}


def _match_row(number: int, mp: dict, notes: dict):
    m = mp["match"]
    alliance = mp["alliance"]
    idx = 1 if mp["station"] == "One" else 2
    teams = m.get("teams") or []
    row = dict(
        id=m["id"], event=mp["eventCode"], label=m["description"], level=m["tournamentLevel"],
        played=m["hasBeenPlayed"], time=m.get("actualStartTime") or m.get("scheduledStartTime"),
        start_ts=ts(m.get("actualStartTime")), alliance=alliance, station=idx,
        partners=[t["teamNumber"] for t in teams if t["alliance"] == alliance and t["teamNumber"] != number],
        opponents=[t["teamNumber"] for t in teams if t["alliance"] != alliance],
        surrogate=mp["surrogate"], no_show=mp["noShow"], dq=mp["dq"], has_scores=False,
        note=notes.get((mp["eventCode"], m["id"])),
    )
    sc = m.get("scores")
    if sc and m["hasBeenPlayed"]:
        me, opp = sc[alliance.lower()], sc["blue" if alliance == "Red" else "red"]
        fp, fn = _flower_counts(me)
        row.update(
            has_scores=True,
            score=me["totalPoints"], score_np=me["totalPointsNp"], opp_score=opp["totalPoints"],
            result="W" if me["totalPoints"] > opp["totalPoints"] else "L" if me["totalPoints"] < opp["totalPoints"] else "T",
            auto=me["autoPoints"], teleop=me["dcPoints"],
            auto_tips=me["autoHiveTips"], tips=me["tips"], dc_tips=me["dcHiveTips"],
            hive_elements=me["dcHivePollenNectar"], hive_pts=me["autoHivePoints"] + me["dcHivePoints"],
            garden=me["dcGardenPollenNectar"], flower_pts=me["dcFlowerPoints"],
            flower_pollen=fp, flower_nectar=fn,
            # these three are for THIS robot specifically (station 1 or 2)
            robot_leave=me[f"autoLeave{idx}"] > 0,
            robot_auto_park=me[f"autoParkPoints{idx}"], robot_park=me[f"dcParkPoints{idx}"],
            penalties=me["penaltyPointsCommitted"], majors=me["majorsCommitted"], minors=me["minorsCommitted"],
            swarm_rp=me["swarmRp"], pollinator1_rp=me["pollinator1Rp"], pollinator2_rp=me["pollinator2Rp"],
        )
    return row


def _summary(rows):
    played = [r for r in rows if r["has_scores"] and not r["no_show"]]
    if not played:
        return None
    return dict(
        n=len(played),
        wins=sum(r["result"] == "W" for r in played), losses=sum(r["result"] == "L" for r in played),
        ties=sum(r["result"] == "T" for r in played),
        avg_score=_avg([r["score_np"] for r in played]), max_score=_max([r["score_np"] for r in played]),
        avg_auto=_avg([r["auto"] for r in played]), avg_teleop=_avg([r["teleop"] for r in played]),
        avg_tips=_avg([r["tips"] for r in played]), max_tips=_max([r["tips"] for r in played]),
        auto_tip_rate=_pct([r["auto_tips"] > 0 for r in played]),
        avg_hive_elements=_avg([r["hive_elements"] for r in played]),
        max_hive_elements=_max([r["hive_elements"] for r in played]),
        avg_garden=_avg([r["garden"] for r in played]),
        avg_flower_pts=_avg([r["flower_pts"] for r in played]),
        nectar_rate=_pct([r["flower_nectar"] > 0 for r in played]),
        leave_rate=_pct([r["robot_leave"] for r in played]),
        auto_park_rate=_pct([r["robot_auto_park"] > 0 for r in played]),
        park_rate=_pct([r["robot_park"] > 0 for r in played]),
        avg_park_pts=_avg([r["robot_park"] for r in played]),
        avg_penalties=_avg([r["penalties"] for r in played]),
        majors=sum(r["majors"] for r in played),
        swarm_rate=_pct([r["swarm_rp"] for r in played]),
        pollinator1_rate=_pct([r["pollinator1_rp"] for r in played]),
        pollinator2_rate=_pct([r["pollinator2_rp"] for r in played]),
    )


def _scouted_summary(notes: list[dict]):
    if not notes:
        return None
    made = [(n["auto_pollen"] or 0) + (n["teleop_pollen"] or 0) for n in notes]
    missed = [n["missed"] or 0 for n in notes]
    shots = sum(made) + sum(missed)
    return dict(
        n=len(notes),
        avg_auto_pollen=_avg([n["auto_pollen"] for n in notes]),
        avg_teleop_pollen=_avg([n["teleop_pollen"] for n in notes]),
        max_pollen=_max(made),
        avg_nectar=_avg([n["nectar"] for n in notes]),
        avg_tips=_avg([n["hive_tips"] for n in notes]),
        accuracy=round(100 * sum(made) / shots) if shots else None,
        breakdowns=sum(1 for n in notes if n["broke_down"]),
        defense=sum(1 for n in notes if n["defense"]),
        avg_rating=_avg([n["rating"] for n in notes]),
    )


def build(number: int, refresh=False):
    t = ftcscout.team(number, refresh=refresh)
    if not t:
        return None
    notes = db.match_notes(number)
    events = {}
    for ep in t["events"]:
        ev = ep["event"]
        events[ev["code"]] = dict(event=ev, stats=ep.get("stats"), matches=[])
    for mp in t["matches"]:
        ev = events.get(mp["eventCode"])
        if ev is not None:
            ev["matches"].append(_match_row(number, mp, notes))
    for ev in events.values():
        ev["matches"].sort(key=lambda r: (LEVEL_ORDER.get(r["level"], 9), r["start_ts"] or 0, r["id"]))
        ev["summary"] = _summary(ev["matches"])
    ordered = sorted(events.values(), key=lambda e: e["event"]["start"], reverse=True)

    all_rows = [r for e in ordered for r in e["matches"]]
    with_stats = [e for e in ordered if e["stats"] and e["summary"]]
    best_opr = max((e["stats"]["opr"]["totalPointsNp"] for e in with_stats), default=None)

    # Upcoming events from the official API (FTCScout may not list them yet).
    today = date.today().isoformat()
    upcoming = []
    for e in ftcevents.team_events(number, refresh=refresh):
        start = (e.get("dateStart") or "")[:10]
        if start >= today:
            upcoming.append(dict(code=e["code"], name=e["name"], start=start,
                                 venue=e.get("venue"), city=e.get("city")))
    upcoming.sort(key=lambda e: e["start"])

    note_list = list(notes.values())
    shots = db.team_shots(number)
    cv = dict(n=len(shots), avg_shots=_avg([s["shots"] for s in shots]),
              avg_auto=_avg([s["auto_shots"] for s in shots]), avg_endgame=_avg([s["endgame_shots"] for s in shots]),
              max_shots=_max([s["shots"] for s in shots])) if shots else None
    return dict(
        cv=cv,
        team=t, info=ftcevents.team_info(number), events=ordered, upcoming=upcoming,
        season=_summary(all_rows), latest=with_stats[0] if with_stats else None, best_opr=best_opr,
        quick=t.get("quickStats"), team_note=db.team_note(number),
        scouted=_scouted_summary(note_list),
    )
