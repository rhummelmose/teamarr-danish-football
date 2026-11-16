"""Betinia Ligaen's official website widget API.

Discover the tournament and public widget configuration from the schedule page.
The public embed token is loaded at runtime, never bundled or logged. It is not
a subscriber API key and does not grant access to video or private account data.
"""

import json
import logging
import re
from datetime import UTC, date, datetime
from urllib.parse import urlencode, urljoin, urlparse

from .html import Tree
from .http import CachedHTTP, SourceError
from .models import Club, Fixture

LOG = logging.getLogger(__name__)
PAGE = "https://1-division.dk/kampprogram"
API = "https://api.superliga.dk"
LEAGUE = "den.2"


def parse_fixture(row):
    if int(row.get("tournamentTemplateId", 0)) != 85:
        raise ValueError("Unexpected competition")
    kickoff = datetime.fromisoformat(row["startDate"].replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError("API kickoff lacks timezone")
    props = row.get("properties") or {}
    states = {"notstarted": "scheduled", "inprogress": "live", "live": "live",
              "finished": "final", "postponed": "postponed", "cancelled": "cancelled",
              "canceled": "cancelled", "interrupted": "postponed", "abandoned": "cancelled"}
    state = states.get(str(row.get("statusType", "")).lower())
    if state is None:
        raise ValueError("Unknown fixture status")

    def club(side):
        if row.get(side + "IsToBeDecided"):
            raise ValueError("Team is not yet known")
        ident = str(int(row[side + "Id"]))
        name = str(row[side + "Name"]).strip()
        if not name:
            raise ValueError("Missing team name")
        return Club(ident, name, row.get(side + "ShortName") or name,
                    f"https://dxugi372p6nmc.cloudfront.net/spdk/current/256x256/{ident}/teamlogo.png")

    score = row.get("score") or {}
    return Fixture(
        id=str(int(row["eventId"])), league=LEAGUE, home=club("home"), away=club("away"),
        kickoff=kickoff.astimezone(UTC), status=state,
        venue=props.get("venueName", ""),
        home_score=score.get("home") if state in {"live", "final"} else None,
        away_score=score.get("away") if state in {"live", "final"} else None,
        time_tbd=props.get("startDateTimeToBeDecided") == "yes",
        source_url=f"https://1-division.dk/sports-innovation/matches/{row['eventId']}",
        season=int(row["tournamentYear"].split("/")[0]),
        round=int(row["round"]) if str(row.get("round", "")).isdigit() else None,
        broadcast=(row.get("channel") or {}).get("name", ""),
    )


class BetiniaClient:
    league = LEAGUE

    def __init__(self, http=None):
        self.http = http or CachedHTTP()

    def _config(self):
        tree = Tree(self.http.get(PAGE, ttl=21600)).root
        widgets = list(tree.find("si-lb-widget"))
        if not any(w.attrs.get("tournament-id") == "85" for w in widgets):
            raise SourceError("Betinia schedule widget changed")
        scripts = [urljoin(PAGE, s.attrs.get("src", "")) for s in tree.find("script")]
        config_url = next((s for s in scripts if urlparse(s).hostname == "lb.tjekscores.dk"
                           and urlparse(s).path.endswith("/config.js")), None)
        if not config_url:
            raise SourceError("Betinia public widget configuration not found")
        config_js = self.http.get(config_url, ttl=21600)
        match = re.search(r"__SI_LB_CONFIG\s*=\s*(\{.*?\});", config_js, re.S)
        if not match:
            raise SourceError("Betinia widget configuration changed")
        config = json.loads(match[1])
        if not config.get("token"):
            raise SourceError("Betinia public widget access unavailable")
        return config

    def _api(self, path, params, ttl=900):
        config = self._config()
        query = {"locale": "da", "appName": "dk.releaze.livecenter.spdk",
                 "access_token": config["token"], "env": "production", **params}
        # Fixed host: a compromised config cannot redirect token-bearing requests.
        url = API + path + "?" + urlencode(query)
        try:
            return json.loads(self.http.get(url, ttl=ttl))
        except (ValueError, TypeError):
            self.http.invalidate(url)
            raise SourceError("Betinia returned invalid JSON") from None

    def fixtures(self, year=None):
        info = self._api("/tournaments/85", {}, ttl=3600)
        if year is None:
            season = info["currentSeason"]["id"]
        else:
            season = next((s["id"] for s in info["seasons"]
                           if s["year"].split("/")[0] == str(year)), None)
            if season is None:
                return []
        payload = self._api("/events-v2", {"seasonId": season})
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise SourceError("Betinia fixture response schema changed")
        fixtures = {}
        for row in payload["events"]:
            try:
                event = parse_fixture(row)
                fixtures[event.id] = event
            except (ValueError, KeyError, TypeError):
                LOG.warning("[BETINIA] Skipped incomplete/unknown fixture (id=%s)", row.get("eventId"))
        if payload["events"] and not fixtures:
            raise SourceError("No Betinia fixture could be parsed")
        return sorted(fixtures.values(), key=lambda f: (f.kickoff, f.id))

    def events(self, day: date):
        # Danish seasons run July–June; filtering uses the UTC calendar like Teamarr.
        year = day.year if day.month >= 7 else day.year - 1
        return [f for f in self.fixtures(year) if f.kickoff.date() == day]
