"""Event-day view: our schedule, who we're with, how hard each match looks, and what to do about it."""
import math
import statistics
from concurrent.futures import ThreadPoolExecutor

from . import ftcevents, ftcscout, report


# ---------------------------------------------------------------- team profiles
def _profile(number, r):
    if not r:
        return dict(number=number, name="?", known=False)
    q, s, tn, sc, cv = r["quick"], r["season"] or {}, r["team_note"] or {}, r["scouted"] or {}, r["cv"] or {}
    return dict(
        number=number, name=r["team"]["name"], known=bool(s and q),
        opr=q["tot"]["value"] if q else None, auto=q["auto"]["value"] if q else None,
        dc=q["dc"]["value"] if q else None, world_rank=q["tot"]["rank"] if q else None,
        matches=s.get("n", 0), record=f"{s['wins']}-{s['losses']}-{s['ties']}" if s else None,
        leave_rate=s.get("leave_rate"), auto_park_rate=s.get("auto_park_rate"), park_rate=s.get("park_rate"),
        auto_tip_rate=s.get("auto_tip_rate"), avg_tips=s.get("avg_tips"), nectar_rate=s.get("nectar_rate"),
        avg_penalties=s.get("avg_penalties"), swarm_rate=s.get("swarm_rate"),
        pollinator1_rate=s.get("pollinator1_rate"), pollinator2_rate=s.get("pollinator2_rate"),
        elements=tn.get("elements"), drivetrain=tn.get("drivetrain"), pit_notes=tn.get("notes"),
        scouted_n=sc.get("n", 0), breakdowns=sc.get("breakdowns", 0), accuracy=sc.get("accuracy"),
        cv_shots=cv.get("avg_shots"),
    )


def profiles(numbers):
    numbers = sorted(set(numbers))

    def one(n):
        try:
            return n, _profile(n, report.build(n))
        except ftcscout.ApiError:
            return n, _profile(n, None)
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(one, numbers))


# ---------------------------------------------------------------- predictions
def win_prob(ours, theirs):
    sd = max(12.0, 0.3 * (ours + theirs) / 2)  # FTC scores swing roughly ±30%
    return 0.5 * (1 + math.erf((ours - theirs) / sd / math.sqrt(2)))


def difficulty(p):
    if p >= 0.75:
        return "Easy", "easy"
    if p >= 0.57:
        return "Favorable", "fav"
    if p >= 0.43:
        return "Toss-up", "even"
    if p >= 0.25:
        return "Hard", "hard"
    return "Very hard", "vhard"


def _opr(p, fallback):
    return p["opr"] if p.get("opr") is not None else fallback


def _pct(v):
    return f"{v:.0f}%" if v is not None else "?"


def suggestions(us, partner, opps, p_win, fallback):
    """Plain-language tips. us/partner/opps are profiles (partner may be None in odd playoff cases)."""
    tips = []
    t = lambda p: f"{p['number']}"  # noqa: E731
    if partner and not partner["known"]:
        tips.append(f"No match data for partner {t(partner)} yet. Talk to them in the pits about their auto and what they score.")
    if partner and partner["known"] and us["known"]:
        if partner["dc"] > us["dc"] * 1.3:
            tips.append(f"{t(partner)} is the stronger teleop scorer (OPR {partner['dc']:.0f} vs our {us['dc']:.0f}). "
                        "Keep their shooting lane clear and push pollen toward them.")
        elif us["dc"] > partner["dc"] * 1.3:
            tips.append(f"We're the main scorer (teleop OPR {us['dc']:.0f} vs {partner['dc']:.0f}). "
                        f"Ask {t(partner)} to gather pollen, park, or play defense instead of competing for the same lane.")
        else:
            tips.append("Even scoring partner: split the field so you aren't fighting for the same pollen.")
        if (partner["auto"] or 0) >= 10 and (us["auto"] or 0) >= 10:
            tips.append(f"Both robots run a real auto (auto OPR {us['auto']:.0f} / {partner['auto']:.0f}). "
                        "Agree on start positions and paths before queuing so you don't collide.")
        if partner["leave_rate"] is not None and partner["leave_rate"] < 70:
            tips.append(f"{t(partner)} only leaves the start zone in {_pct(partner['leave_rate'])} of autos. Remind them those points are free.")
        if partner["auto_tip_rate"] is not None and partner["auto_tip_rate"] >= 60:
            tips.append(f"{t(partner)}'s alliances tip the hive in auto {_pct(partner['auto_tip_rate'])} of the time. Plan who fills the hive first.")
        if partner["park_rate"] is not None and partner["park_rate"] < 70:
            tips.append(f"{t(partner)} parks at the end in only {_pct(partner['park_rate'])} of matches. Call 'park!' with about 10 s left.")
        if (partner["avg_penalties"] or 0) >= 10:
            tips.append(f"{t(partner)}'s matches average {partner['avg_penalties']:.0f} penalty points given away. Talk through contact and pinning rules.")
        if partner["breakdowns"]:
            tips.append(f"Our scouts saw {t(partner)} break down in {partner['breakdowns']} match(es). Have a plan to score alone.")
        if partner["elements"]:
            tips.append(f"Pit notes: {t(partner)} scores {partner['elements']}.")
    known_opps = [o for o in opps if o["known"]]
    if known_opps:
        star = max(known_opps, key=lambda o: o["dc"] or 0)
        weak = min(opps, key=lambda o: _opr(o, fallback))
        if len(opps) > 1 and (star["dc"] or 0) > 1.8 * max(1, _opr(weak, fallback) - (weak.get("auto") or 0)):
            tips.append(f"{t(star)} carries the other alliance (teleop OPR {star['dc']:.0f}). If we're behind, "
                        "slowing them down with legal defense may be worth more than our weaker robot's points.")
        nectar = [o for o in known_opps if (o["nectar_rate"] or 0) >= 40]
        ours_nectar = [p for p in (us, partner) if p and p["known"] and (p["nectar_rate"] or 0) >= 40]
        if nectar:
            tips.append(f"Opponents ({', '.join(t(o) for o in nectar)}) often use nectar in the last minute. "
                        "Watch flower ownership: the top nectar decides who owns a flower."
                        + ("" if ours_nectar else " Nobody on our alliance usually scores nectar, so decide who will contest it."))
        sloppy = [o for o in known_opps if (o["avg_penalties"] or 0) >= 10]
        if sloppy:
            tips.append(f"{', '.join(t(o) for o in sloppy)} give away a lot of penalty points. Play clean and don't get pulled into contact.")
    if p_win < 0.43:
        rp = [p for p in (us, partner) if p and p["known"]]
        swarm = max((p["swarm_rate"] or 0 for p in rp), default=0)
        tips.append("Underdog match: still go for ranking points. "
                    + (f"Swarm RP is realistic (we/partner get it in up to {swarm:.0f}% of matches)." if swarm >= 50
                       else "Make sure both robots leave and park, and avoid penalties."))
    elif p_win >= 0.75:
        tips.append("We should win this one. Push for the bonus RPs (Swarm/Pollinator) and play safe, with no penalties.")
    return tips


# ---------------------------------------------------------------- event view
def _alliance_of(station):
    return "Red" if station.startswith("Red") else "Blue"


def event_view(code: str, our: int, refresh=False):
    ev = ftcscout.event(code, refresh=refresh)
    official_teams = ftcevents.event_teams(code)
    numbers = {t["teamNumber"] for t in official_teams} | {t["teamNumber"] for t in (ev or {}).get("teams") or []}
    sched = ftcevents.schedule(code, refresh=refresh)
    for m in sched:
        numbers |= {t["teamNumber"] for t in m["teams"] if t.get("teamNumber")}
    profs = profiles(numbers)
    known = [p["opr"] for p in profs.values() if p.get("opr") is not None]
    fallback = statistics.median(known) * 0.7 if known else 20.0  # unknown team: assume a bit below average

    live = {t["teamNumber"]: t.get("stats") for t in (ev or {}).get("teams") or []}
    results = {r["description"]: r for r in ftcevents.results(code, refresh=refresh)}

    ours = []
    for m in sched:
        st = {t["teamNumber"]: t["station"] for t in m["teams"] if t.get("teamNumber")}
        if our not in st:
            continue
        al = _alliance_of(st[our])
        mates = [n for n, s in st.items() if _alliance_of(s) == al and n != our]
        opp = [n for n, s in st.items() if _alliance_of(s) != al]
        us_p, partner = profs.get(our), profs.get(mates[0]) if mates else None
        opps = [profs[n] for n in opp]
        pred_us = sum(_opr(profs[n], fallback) for n in [our, *mates])
        pred_them = sum(_opr(p, fallback) for p in opps)
        p = win_prob(pred_us, pred_them)
        label, cls = difficulty(p)
        res = results.get(m["description"])
        played = None
        if res and res.get("scoreRedFinal") is not None and res.get("postResultTime"):
            a, b = (res["scoreRedFinal"], res["scoreBlueFinal"]) if al == "Red" else (res["scoreBlueFinal"], res["scoreRedFinal"])
            played = dict(us=a, them=b, result="W" if a > b else "L" if a < b else "T")
        ours.append(dict(
            description=m["description"], level=m["tournamentLevel"], time=m.get("startTime"), field=m.get("field"),
            alliance=al, partners=[profs[n] for n in mates], opponents=opps,
            pred_us=round(pred_us), pred_them=round(pred_them), p_win=round(p * 100), difficulty=label, diff_class=cls,
            played=played, tips=suggestions(us_p, partner, opps, p, fallback),
        ))
    nxt = next((m for m in ours if not m["played"]), None)
    table = sorted(profs.values(), key=lambda p: -(p.get("opr") or -1))
    for p in table:
        p["live"] = live.get(p["number"])
    return dict(event=ev, code=code, our=our, our_profile=profs.get(our), matches=ours, next=nxt,
                schedule_out=bool(sched), teams=table, n_matches=len(sched), fallback=fallback)
