"""FTCScout public GraphQL API (https://ftcscout.org) - no key needed."""
import requests

from . import cache
from .config import SEASON

URL = "https://api.ftcscout.org/graphql"
FRESH = 10 * 60  # results are refreshed every 10 minutes

ALLIANCE_FIELDS = """
  autoLeave1 autoLeave2 autoLeavePoints autoParkPoints1 autoParkPoints2 autoParkPoints
  autoHiveTips autoHivePoints dcHiveTips dcHivePollenNectar dcHivePoints
  redAllianceFlowerState blueAllianceFlowerState scoringFlowerState audienceFlowerState
  dcFlowerPoints dcGardenPollenNectar dcGardenPoints dcParkPoints1 dcParkPoints2 dcParkPoints
  tips swarmRp pollinator1Rp pollinator2Rp autoPoints dcPoints
  minorsCommitted majorsCommitted penaltyPointsCommitted penaltyPointsByOpp
  totalPointsNp totalPoints
"""

GROUP_FIELDS = """
  autoLeavePointsIndividual autoParkPointsIndividual autoHivePoints dcHivePoints dcFlowerPoints
  dcGardenPoints dcParkPointsIndividual tips swarmRp pollinator1Rp pollinator2Rp
  autoPoints dcPoints penaltyPointsCommitted totalPointsNp totalPoints
"""

TEAM_QUERY = """
query($n: Int!, $s: Int!) {
  teamByNumber(number: $n) {
    number name schoolName rookieYear website sponsors
    location { city state country }
    quickStats(season: $s) { tot { value rank } auto { value rank } dc { value rank } eg { value rank } count }
    events(season: $s) {
      eventCode
      event { code name start end timezone type started finished
              location { city state country } liveStreamURL webcasts
              livestreamsByDay { day liveStreamURL webcasts } }
      stats { ... on TeamEventStats2026 {
        rank rp wins losses ties dqs qualMatchesPlayed
        avg { %(g)s } opr { %(g)s } max { %(g)s } } }
    }
    matches(season: $s) {
      eventCode station alliance surrogate noShow dq onField
      match { id matchNum series description tournamentLevel hasBeenPlayed
              actualStartTime scheduledStartTime
              teams { teamNumber alliance station }
              scores { ... on MatchScores2026 { red { %(a)s } blue { %(a)s } } } }
    }
  }
}
""" % {"g": GROUP_FIELDS, "a": ALLIANCE_FIELDS}

SEARCH_QUERY = """
query($q: String!) { teamsSearch(searchText: $q, limit: 15) { number name location { city state country } } }
"""


class ApiError(Exception):
    pass


def _gql(query, variables, cache_key, max_age=FRESH, refresh=False):
    if not refresh:
        hit = cache.get(cache_key, max_age)
        if hit is not None:
            return hit
    try:
        r = requests.post(URL, json={"query": query, "variables": variables}, timeout=30)
        body = r.json()
        if body.get("errors"):
            raise ApiError("; ".join(e["message"] for e in body["errors"]))
        return cache.put(cache_key, body["data"])
    except (requests.RequestException, ValueError) as e:
        stale = cache.get_stale(cache_key)
        if stale is not None:  # offline at the venue: use whatever we have
            return stale
        raise ApiError(f"FTCScout unreachable: {e}") from e


def team(number: int, season: int = SEASON, refresh=False):
    data = _gql(TEAM_QUERY, {"n": number, "s": season}, f"ftcscout:team:{season}:{number}", refresh=refresh)
    return data["teamByNumber"]


EVENTS_ON_QUERY = """
query($s: Int!, $d: Date!) {
  eventsSearch(season: $s, start: $d, end: $d, limit: 400) {
    code name start end type started ongoing finished timezone
    location { city state country }
  }
}
"""

EVENT_QUERY = """
query($s: Int!, $c: String!) {
  eventByCode(season: $s, code: $c) {
    code name start end timezone type started ongoing finished website liveStreamURL
    location { venue city state country }
    teams { teamNumber team { name } stats { ... on TeamEventStats2026 { rank rp wins losses ties qualMatchesPlayed opr { totalPointsNp } } } }
    matches { id description tournamentLevel series matchNum actualStartTime scheduledStartTime hasBeenPlayed
              teams { teamNumber alliance station } }
  }
}
"""


def events_on(day: str, season: int = SEASON):
    data = _gql(EVENTS_ON_QUERY, {"s": season, "d": day}, f"ftcscout:eventson:{season}:{day}", max_age=3600)
    return data["eventsSearch"]


def event(code: str, season: int = SEASON, refresh=False):
    data = _gql(EVENT_QUERY, {"s": season, "c": code}, f"ftcscout:event:{season}:{code}", max_age=120,
                refresh=refresh)
    return data["eventByCode"]


def search_teams(text: str):
    data = _gql(SEARCH_QUERY, {"q": text}, f"ftcscout:search:{text.lower()}", max_age=24 * 3600)
    return data["teamsSearch"]
