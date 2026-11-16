"""Run against the real, pinned Teamarr core (no fake interface stubs)."""

from datetime import date
import importlib.util
import unittest

from teamarr_danish.aliga import ALigaClient
from teamarr_danish.http import CachedHTTP
from test_providers import html


@unittest.skipUnless(importlib.util.find_spec("teamarr"), "Teamarr source/runtime not installed")
class TeamarrContractTests(unittest.TestCase):
    def test_provider_contract_and_scoped_ids(self):
        from teamarr.core import SportsProvider
        from teamarr_danish.provider import ALigaProvider

        provider = ALigaProvider(client=ALigaClient(CachedHTTP(fetch=lambda _: html())))
        self.assertIsInstance(provider, SportsProvider)
        events = provider.get_events("den.w.1", date(2026, 11, 21))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.provider, "aliga")
        self.assertEqual(event.home_team.provider, "aliga")
        self.assertEqual(event.home_team.league, "den.w.1")
        self.assertEqual(provider.get_events("den.1", date(2026, 11, 21)), [])
        self.assertEqual(provider.get_event(event.id, "den.w.1").id, event.id)
        self.assertEqual(provider.get_team("431", "den.w.1").name, "AGF")
        self.assertEqual(len(provider.get_league_teams("den.w.1")), 2)
        self.assertIsNone(provider.get_team("431", "den.1"))

    def test_disabled_mapping_is_respected(self):
        from teamarr_danish.provider import ALigaProvider

        class Disabled:
            def supports_league(self, league, provider):
                return False

        p = ALigaProvider(league_mapping_source=Disabled())
        self.assertEqual(p.get_supported_leagues(), [])
        self.assertEqual(p.get_events("den.w.1", date.today()), [])
