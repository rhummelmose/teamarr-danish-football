"""Adapters implementing Teamarr's SportsProvider interface."""

import logging
from datetime import UTC, datetime, timedelta

from teamarr.core import Event, EventStatus, SportsProvider, Team, Venue

from .aliga import ALigaClient
from .betinia import BetiniaClient
from .http import SourceError

LOG = logging.getLogger(__name__)


class DanishProvider(SportsProvider):
    provider_name = ""
    league_code = ""
    client_type = None

    def __init__(self, client=None, league_mapping_source=None):
        self.client = client or self.client_type()
        self.mapping = league_mapping_source

    @property
    def name(self):
        return self.provider_name

    def supports_league(self, league):
        return (league == self.league_code and (self.mapping is None
                or self.mapping.supports_league(league, self.name)))

    def get_supported_leagues(self):
        return [self.league_code] if self.supports_league(self.league_code) else []

    def _team(self, club):
        return Team(id=club.id, provider=self.name, name=club.name, short_name=club.name,
                    abbreviation=club.short_name, league=self.league_code, sport="soccer",
                    logo_url=club.logo)

    def _event(self, fixture):
        return Event(
            id=fixture.id, provider=self.name,
            name=f"{fixture.home.name} vs {fixture.away.name}",
            short_name=f"{fixture.home.short_name} v {fixture.away.short_name}",
            start_time=fixture.kickoff, home_team=self._team(fixture.home),
            away_team=self._team(fixture.away), status=EventStatus(state=fixture.status),
            league=self.league_code, sport="soccer", home_score=fixture.home_score,
            away_score=fixture.away_score,
            venue=Venue(name=fixture.venue, country="Denmark") if fixture.venue else None,
            broadcasts=[fixture.broadcast] if fixture.broadcast else [],
            season_year=fixture.season, season_type="regular", time_tbd=fixture.time_tbd,
            week=fixture.round,
        )

    def _read(self, operation):
        try:
            return operation()
        except (SourceError, ValueError, KeyError, TypeError):
            LOG.warning("[%s] Fixture source unavailable or changed; no data returned", self.name)
            return []

    def get_events(self, league, date):
        if not self.supports_league(league):
            return []
        return [self._event(f) for f in self._read(lambda: self.client.events(date))]

    def get_team_schedule(self, team_id, league, days_ahead=14):
        if not self.supports_league(league):
            return []
        today = datetime.now(UTC).date()
        end = today + timedelta(days=days_ahead)
        return [self._event(f) for f in self._read(self.client.fixtures)
                if today <= f.kickoff.date() <= end and str(team_id) in {f.home.id, f.away.id}]

    def get_event(self, event_id, league):
        if not self.supports_league(league):
            return None
        return next((self._event(f) for f in self._read(self.client.fixtures)
                     if f.id == str(event_id)), None)

    def get_league_teams(self, league):
        if not self.supports_league(league):
            return []
        clubs = {}
        for fixture in self._read(self.client.fixtures):
            clubs[fixture.home.id] = self._team(fixture.home)
            clubs[fixture.away.id] = self._team(fixture.away)
        return list(clubs.values())

    def get_team(self, team_id, league):
        return next((t for t in self.get_league_teams(league) if t.id == str(team_id)), None)


class BetiniaProvider(DanishProvider):
    provider_name = "betinia"
    league_code = "den.2"
    client_type = BetiniaClient


class ALigaProvider(DanishProvider):
    provider_name = "aliga"
    league_code = "den.w.1"
    client_type = ALigaClient
