"""Provider-neutral records; the CLI has no dependency on Teamarr."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Club:
    id: str
    name: str
    short_name: str
    logo: str | None = None


@dataclass(frozen=True)
class Fixture:
    id: str
    league: str
    home: Club
    away: Club
    kickoff: datetime
    status: str
    venue: str = ""
    home_score: int | None = None
    away_score: int | None = None
    time_tbd: bool = False
    source_url: str = ""
    season: int | None = None
    round: int | None = None
    broadcast: str = ""
