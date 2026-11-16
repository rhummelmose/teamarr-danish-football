"""A-Ligaen schedules from the league's own DBU-backed match programme."""

import logging
import re
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, quote, urljoin, urlparse
from zoneinfo import ZoneInfo

from .html import Tree
from .http import CachedHTTP, SourceError
from .models import Club, Fixture

LOG = logging.getLogger(__name__)
PAGE = "https://www.a-liga.dk/kampe/"
LEAGUE = "den.w.1"
COPENHAGEN = ZoneInfo("Europe/Copenhagen")
MONTHS = {name: i for i, name in enumerate(
    "januar februar marts april maj juni juli august september oktober november december".split(), 1)}


def parse_datetime(text):
    match = re.search(r"(\d{1,2})\.\s*([a-zæøå]+)\s+(\d{4})(?:\s*-\s*(\d{1,2}):(\d{2}))?",
                      text.lower())
    if not match or match[2] not in MONTHS:
        raise ValueError("Unrecognized Danish match date")
    tbd = match[4] is None
    # A documented date-only placeholder; Teamarr's time_tbd prevents false precision.
    naive = datetime(int(match[3]), MONTHS[match[2]], int(match[1]),
                     int(match[4] or 12), int(match[5] or 0))
    a, b = naive.replace(tzinfo=COPENHAGEN, fold=0), naive.replace(tzinfo=COPENHAGEN, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise ValueError("Ambiguous/nonexistent DST kickoff; do not guess")
    return a.astimezone(UTC), tbd


def parse_schedule(html, now=None):
    now = now or datetime.now(UTC)
    tree = Tree(html).root
    body = tree.first("body")
    if body.attrs.get("data-league") != "4":
        raise SourceError("Page is not the A-Liga fixture programme")
    wrapper = tree.first(cls="match-program-list-wrap")
    rows = list(wrapper.find(cls="match"))
    if not wrapper.tag:
        raise SourceError("A-Liga fixture layout changed")
    if not rows:
        raise SourceError("A-Liga programme contains no fixture rows")
    fixtures = {}
    season = None
    for element in wrapper.children:
        if not hasattr(element, "tag"):
            continue
        if element.tag == "h2":
            # Never ingest a cup/B-league programme merely because it shares the page.
            match = re.search(r"A-Liga.*?(20\d{2})/", element.text, re.I)
            season = int(match[1]) if match else None
            continue
        if season is None:
            continue
        for row in element.find(cls="match"):
            try:
                kickoff, tbd = parse_datetime(row.first(cls="datetime").text)
                links = [x.attrs.get("href", "") for x in row.find("a")]
                match_id = next(parse_qs(urlparse(link).query)["matchid"][0]
                                for link in links if "matchid" in parse_qs(urlparse(link).query))
                if not match_id.isdigit():
                    raise ValueError("Invalid match identity")
                teams = list(row.find(cls="team"))
                if len(teams) != 2:
                    raise ValueError("Expected home and away teams")

                def club(node, side):
                    ident = str(int(row.attrs["data-" + side]))
                    name = node.first(cls="teamname").text
                    if not name:
                        raise ValueError("Missing team name")
                    src = node.first("img").attrs.get("src")
                    image = urljoin(PAGE, src) if src else None
                    if image and urlparse(image).hostname not in {"file.dbu.dk", "www.a-liga.dk"}:
                        image = None
                    if image:
                        image = quote(image, safe=":/%?=&-_.~")
                    return Club(ident, name, name, image)

                score = re.fullmatch(r"(\d+)\s*-\s*(\d+)", row.first(cls="score").text)
                text = row.text.lower()
                state = "scheduled"
                if "aflyst" in text:
                    state = "cancelled"
                elif "udsat" in text or "udskudt" in text:
                    state = "postponed"
                elif score and kickoff <= now:
                    # This page has scores but no reliable live/final flag. Only mark
                    # final after four hours; never infer a result from elapsed time alone.
                    state = "final" if (now - kickoff).total_seconds() >= 14400 else "live"
                event = Fixture(
                    id=f"{season}:{match_id}", league=LEAGUE,
                    home=club(teams[0], "home"), away=club(teams[1], "away"),
                    kickoff=kickoff, status=state, venue=row.first(cls="stadium").text,
                    home_score=int(score[1]) if score else None,
                    away_score=int(score[2]) if score else None, time_tbd=tbd,
                    source_url=f"https://www.a-liga.dk/kamp/?matchid={match_id}", season=season,
                )
                fixtures[event.id] = event
            except (ValueError, KeyError, TypeError, StopIteration):
                LOG.warning("[ALIGA] Skipped incomplete/ambiguous fixture row")
    if not fixtures:
        raise SourceError("No A-Liga fixtures could be parsed")
    return sorted(fixtures.values(), key=lambda f: (f.kickoff, f.id))


class ALigaClient:
    league = LEAGUE

    def __init__(self, http=None):
        self.http = http or CachedHTTP()

    def fixtures(self, year=None):
        # No hardcoded pool or season ID: all published A-Liga phases are discovered.
        events = parse_schedule(self.http.get(PAGE))
        return events if year is None else [f for f in events if f.season == year]

    def events(self, day: date):
        return [f for f in self.fixtures() if f.kickoff.date() == day]
