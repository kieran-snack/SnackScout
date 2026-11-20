"""Competition hub: every match at an event (not just ours), live rankings, event highs, alliance selection."""
from datetime import datetime

from . import ftcevents
from .strategy import _opr, event_view, win_prob


def ts_utc(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def match_key(level, series, num):
    """One key per match across FTC Events ('QUALIFICATION'/'PLAYOFF') and FTCScout ('Quals'/'DoubleElim')."""
    lvl = (level or "").upper()
    if lvl.startswith("QUAL"):
        return f"Q-{num}"
    if lvl.startswith("PRACT"):
        return f"P-{num}"
    return f"PO-{series or 0}-{num}"


def _short(desc, key):
    if key.startswith("Q-"):
        return key
    return (desc or key).replace("Playoff ", "P").replace("Match ", "M").replace("Final ", "F")


def _sum(nums, profs, fallback):
    return sum(_opr(profs[n], fallback) if n in profs else fallback for n in nums)


def _insight(red, blue, profs, p_red, fallback):
    """One line about a match we're not in: who's favored and who to watch."""
    if not red + blue:
        return None
    strongest = max(red + blue, key=lambda n: _opr(profs.get(n, {}), fallback))
    side = "Red" if strongest in red else "Blue"
    if 0.43 <= p_red <= 0.57:
        return f"Toss-up. Watch {strongest} ({side}), the top scorer on the field."
    fav = "Red" if p_red > 0.5 else "Blue"
    return f"{fav} favored ({round(max(p_red, 1 - p_red) * 100)}%). {strongest} ({side}) is the one to watch."


def event_hub(code: str, our: int, refresh=False):
    view = event_view(code, our, refresh=refresh)  # our matches + strategy tips + team profiles
    ev = view["event"] or {}
    fallback = view["fallback"]
    profs = {p["number"]: p for p in view["teams"]}
    sched = ftcevents.schedule(code, refresh=refresh)
    results = {r["description"]: r for r in ftcevents.results(code, refresh=refresh)}
    scout = {match_key(m["tournamentLevel"], m.get("series"), m.get("matchNum")): m for m in ev.get("matches") or []}
    ours_by_desc = {m["description"]: m for m in view["matches"]}

    rows = []
    if sched:
        for m in sched:
            teams = [t for t in m["teams"] if t.get("teamNumber")]
            rows.append(dict(level=m["tournamentLevel"], series=m.get("series"), num=m["matchNumber"], desc=m["description"],
                             time=m.get("startTime"), field=m.get("field"),
                             red=[t["teamNumber"] for t in teams if t["station"].startswith("Red")],
                             blue=[t["teamNumber"] for t in teams if t["station"].startswith("Blue")]))
    else:  # no FTC Events schedule: fall back to FTCScout's list
        for m in ev.get("matches") or []:
            rows.append(dict(level=m["tournamentLevel"], series=m.get("series"), num=m["matchNum"], desc=m["description"],
                             time=m.get("scheduledStartTime"), field=None,
                             red=[t["teamNumber"] for t in m["teams"] if t["alliance"] == "Red"],
                             blue=[t["teamNumber"] for t in m["teams"] if t["alliance"] == "Blue"]))

    matches = []
    for r in rows:
        key = match_key(r["level"], r["series"], r["num"])
        sm = scout.get(key)
        res = results.get(r["desc"])
        pr, pb = _sum(r["red"], profs, fallback), _sum(r["blue"], profs, fallback)
        p_red = win_prob(pr, pb)
        played = bool(res and res.get("scoreRedFinal") is not None and res.get("postResultTime"))
        side = "Red" if our in r["red"] else "Blue" if our in r["blue"] else None
        mine = ours_by_desc.get(r["desc"]) if side else None
        rs, bs = (res["scoreRedFinal"], res["scoreBlueFinal"]) if played else (None, None)
        winner = None if not played else "Red" if rs > bs else "Blue" if bs > rs else "Tie"
        fav = "Red" if p_red >= 0.5 else "Blue"
        matches.append(dict(
            key=key, label=_short(r["desc"], key), description=r["desc"], level=r["level"], time=r["time"], field=r["field"],
            red=r["red"], blue=r["blue"], played=played, red_score=rs, blue_score=bs,
            red_auto=res.get("scoreRedAuto") if played else None, blue_auto=res.get("scoreBlueAuto") if played else None,
            winner=winner, upset=bool(played and winner not in (fav, "Tie") and abs(p_red - 0.5) > 0.15),
            pred_red=round(pr), pred_blue=round(pb), p_red=round(p_red * 100),
            match_id=sm["id"] if sm else (r["num"] if key.startswith("Q-") else 10000 + (r["series"] or 0) * 100 + r["num"]),
            start_ts=ts_utc(sm.get("actualStartTime")) if sm else None,
            ours=side, tips=mine["tips"] if mine else [], difficulty=mine["difficulty"] if mine else None,
            diff_class=mine["diff_class"] if mine else None, p_win=mine["p_win"] if mine else None,
            insight=None if side else _insight(r["red"], r["blue"], profs, p_red, fallback),
        ))

    played = [m for m in matches if m["played"]]
    highs = {}
    if played:
        hs = max(((m[f"{s}_score"], m, s) for m in played for s in ("red", "blue")), key=lambda x: x[0])
        ha = max(((m[f"{s}_auto"] or 0, m, s) for m in played for s in ("red", "blue")), key=lambda x: x[0])
        margin = max(played, key=lambda m: abs(m["red_score"] - m["blue_score"]))
        close = min(played, key=lambda m: abs(m["red_score"] - m["blue_score"]))
        highs = dict(
            high_score=dict(points=hs[0], match=hs[1]["label"], alliance=hs[2].title(), teams=hs[1][hs[2]]),
            high_auto=dict(points=ha[0], match=ha[1]["label"], alliance=ha[2].title(), teams=ha[1][ha[2]]),
            biggest_win=dict(points=abs(margin["red_score"] - margin["blue_score"]), match=margin["label"],
                             score=f"{max(margin['red_score'], margin['blue_score'])}–{min(margin['red_score'], margin['blue_score'])}"),
            closest=dict(points=abs(close["red_score"] - close["blue_score"]), match=close["label"],
                         score=f"{close['red_score']}–{close['blue_score']}"),
            avg_winning=round(sum(max(m["red_score"], m["blue_score"]) for m in played) / len(played)),
            upsets=sum(1 for m in played if m["upset"]),
        )

    ranks = []  # live rankings: FTC Events first (updated during the event), else FTCScout
    for r in ftcevents.rankings(code, refresh=refresh):
        p = profs.get(r["teamNumber"], {})
        ranks.append(dict(rank=r["rank"], number=r["teamNumber"], name=r.get("teamName") or p.get("name"),
                          rp=r.get("sortOrder1"), wins=r.get("wins"), losses=r.get("losses"), ties=r.get("ties"),
                          played=r.get("matchesPlayed"), opr=p.get("opr")))
    if not ranks:
        for p in profs.values():
            st = p.get("live") or {}
            if st.get("rank"):
                ranks.append(dict(rank=st["rank"], number=p["number"], name=p["name"], rp=st.get("rp"), wins=st.get("wins"),
                                  losses=st.get("losses"), ties=st.get("ties"), played=st.get("qualMatchesPlayed"), opr=p.get("opr")))
    ranks.sort(key=lambda r: r["rank"])

    quals = [m for m in matches if m["key"].startswith("Q-")]
    return dict(view, matches_all=matches, highs=highs, rankings=ranks,
                progress=dict(played=sum(1 for m in quals if m["played"]), total=len(quals)),
                picks=pick_suggestions(profs, our, ranks))


def find_match(hub, key):
    return next((m for m in hub["matches_all"] if m["key"] == key), None)


def pick_suggestions(profs: dict, our: int, ranks: list):
    """Rank possible partners for alliance selection, with reasons a person can check."""
    me = profs.get(our) or {}
    rank_of = {r["number"]: r["rank"] for r in ranks}
    out = []
    for n, p in profs.items():
        if n == our:
            continue
        opr = p.get("opr")
        if opr is None:
            out.append(dict(number=n, name=p.get("name"), score=0, opr=None, rank=rank_of.get(n),
                            reasons=["no match data yet"], flags=[]))
            continue
        score, reasons, flags = opr, [f"OPR {opr:.0f}"], []
        if (p.get("leave_rate") or 0) >= 90:
            score += 3
            reasons.append("always leaves in auto")
        if (p.get("park_rate") or 0) >= 85:
            score += 4
            reasons.append(f"parks {p['park_rate']}%")
        elif p.get("park_rate") is not None and p["park_rate"] < 60:
            score -= 4
            flags.append(f"parks only {p['park_rate']}%")
        if me.get("auto") is not None and p.get("auto") is not None and p["auto"] > me["auto"]:
            score += 0.3 * (p["auto"] - me["auto"])
            reasons.append(f"stronger auto than us ({p['auto']:.0f})")
        if (p.get("auto_tip_rate") or 0) >= 60:
            score += 3
            reasons.append("alliances tip the hive in auto")
        if (p.get("nectar_rate") or 0) >= 40:
            score += 2
            reasons.append("uses nectar")
        if (p.get("avg_penalties") or 0) >= 10:
            score -= 0.4 * p["avg_penalties"]
            flags.append(f"{p['avg_penalties']:.0f} penalty pts/match")
        if p.get("breakdowns"):
            score -= 5 * p["breakdowns"]
            flags.append(f"broke down {p['breakdowns']}× in our scouting")
        if (p.get("matches") or 0) < 4:
            flags.append("little data")
        out.append(dict(number=n, name=p.get("name"), score=round(score, 1), opr=opr, rank=rank_of.get(n),
                        reasons=reasons, flags=flags))
    out.sort(key=lambda x: -x["score"])
    for i, x in enumerate(out):
        x["tier"] = "1st pick" if i < 4 else "2nd pick" if i < 12 else "depth"
    return out
