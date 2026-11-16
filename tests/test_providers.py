from datetime import UTC, date, datetime
import re
import sqlite3
import unittest

from teamarr_danish.aliga import ALigaClient, parse_datetime, parse_schedule
from teamarr_danish.betinia import parse_fixture
from teamarr_danish.http import CachedHTTP, SourceError
from teamarr_danish.install import HINTS, seed


def html(day="21. november 2026 - 13:00", score=" - ", ident="123", extra="", season="2026/27"):
    return f'''<html><body data-league="4"><div class="match-program-list-wrap">
      <h2>A-Liga - Grundspil {season}</h2><div class="match-program-list">
      <div class="match" data-home="431" data-away="981">
       <div class="teams-score"><div class="team"><div class="teamname">AGF</div>
        <img src="https://file.dbu.dk/images/club/431/AGF.png"></div>
       <div class="score">{score}</div><div class="team away">
        <div class="teamname">Br&#xF8;ndby IF</div></div></div>
       <div class="datetime">Lør. {day}</div><div class="stadium">Test Park</div>
       <a href="/kamp/?matchid={ident}">Kampinfo</a>{extra}
      </div></div></div></body></html>'''


ROW = {"eventId": 1234, "tournamentTemplateId": 85,
       "startDate": "2026-11-19T18:00:00.000Z", "statusType": "notstarted",
       "homeId": 1, "awayId": 2, "homeName": "FC Fredericia", "awayName": "Hillerød Fodbold",
       "homeShortName": "FCF", "awayShortName": "HIL", "tournamentYear": "2026/2027",
       "properties": {}, "round": "15", "score": {"home": 0, "away": 0}}


class ALigaTests(unittest.TestCase):
    def test_real_danish_entities_winter_and_summer(self):
        f = parse_schedule(html())[0]
        self.assertEqual(f.away.name, "Brøndby IF")
        self.assertEqual(f.kickoff.isoformat(), "2026-11-21T12:00:00+00:00")
        self.assertEqual(parse_datetime("1. august 2026 - 13:00")[0].hour, 11)

    def test_stable_id_across_kickoff_change(self):
        old = parse_schedule(html())[0]
        new = parse_schedule(html(day="22. november 2026 - 16:00"))[0]
        self.assertEqual(old.id, new.id)
        self.assertNotEqual(old.kickoff, new.kickoff)

    def test_missing_time_is_explicit_tbd(self):
        self.assertTrue(parse_schedule(html(day="21. november 2026"))[0].time_tbd)

    def test_utc_calendar_boundary(self):
        client = ALigaClient(CachedHTTP(fetch=lambda _: html(day="21. november 2026 - 00:30")))
        self.assertEqual(len(client.events(date(2026, 11, 20))), 1)
        self.assertEqual(client.events(date(2026, 11, 21)), [])

    def test_dst_unknown_time_does_not_guess(self):
        for text in ("29. marts 2026 - 02:30", "25. oktober 2026 - 02:30"):
            with self.assertRaises(ValueError):
                parse_datetime(text)

    def test_postponed_and_cancelled(self):
        self.assertEqual(parse_schedule(html(extra="<span>Udskudt</span>"))[0].status, "postponed")
        self.assertEqual(parse_schedule(html(extra="<span>Aflyst</span>"))[0].status, "cancelled")

    def test_scores_not_inferred_from_elapsed_time(self):
        now = datetime(2026, 11, 22, tzinfo=UTC)
        self.assertEqual(parse_schedule(html(), now)[0].status, "scheduled")
        self.assertEqual(parse_schedule(html(score="0 - 0"), now)[0].status, "final")
        self.assertEqual(parse_schedule(html(score="1 - 0"), datetime(2026, 11, 21, 13, tzinfo=UTC))[0].status, "live")

    def test_wrong_page_and_layout_fail_loudly(self):
        for page in ("<html>Unavailable</html>", html().replace('data-league="4"', 'data-league="5"'),
                     html().replace("A-Liga - Grundspil", "B-Liga - Grundspil")):
            with self.assertRaises(SourceError):
                parse_schedule(page)

    def test_duplicate_fixture_is_deduplicated(self):
        page = html()
        start, end = page.index('<div class="match-program-list">'), page.rfind('</div></body>')
        page = page[:end] + page[start:end] + page[end:]
        self.assertEqual(len(parse_schedule(page)), 1)


class BetiniaTests(unittest.TestCase):
    def test_utc_fixture_and_no_premature_zero_score(self):
        f = parse_fixture(ROW)
        self.assertEqual(f.kickoff.hour, 18)
        self.assertEqual(f.status, "scheduled")
        self.assertIsNone(f.home_score)

    def test_wrong_league_and_unknown_status_rejected(self):
        for key, val in [("tournamentTemplateId", 46), ("statusType", "new-status"),
                         ("homeIsToBeDecided", True), ("startDate", "2026-11-19T18:00:00")]:
            with self.assertRaises(ValueError):
                parse_fixture({**ROW, key: val})

    def test_status_score_and_tbd(self):
        self.assertEqual(parse_fixture({**ROW, "statusType": "postponed"}).status, "postponed")
        self.assertEqual(parse_fixture({**ROW, "statusType": "finished"}).home_score, 0)
        self.assertTrue(parse_fixture({**ROW, "properties": {"startDateTimeToBeDecided": "yes"}}).time_tbd)


class CacheTests(unittest.TestCase):
    def test_refresh_after_expiry_without_stale_fallback(self):
        clock = [0]
        calls = []

        def fetch(url):
            calls.append(url)
            if len(calls) == 3:
                raise OSError("secret URL should not escape")
            return str(len(calls))

        cache = CachedHTTP(fetch=fetch, clock=lambda: clock[0], ttl=10)
        self.assertEqual(cache.get("url"), "1")
        self.assertEqual(cache.get("url"), "1")
        clock[0] = 11
        self.assertEqual(cache.get("url"), "2")
        clock[0] = 22
        with self.assertRaises(SourceError) as caught:
            cache.get("url")
        self.assertNotIn("secret", str(caught.exception))
        with self.assertRaises(SourceError):
            cache.get("url")
        self.assertEqual(len(calls), 3)
        clock[0] = 83
        self.assertEqual(cache.get("url"), "4")


class InstallTests(unittest.TestCase):
    def test_womens_handball_is_not_classified_as_football(self):
        women = next(pattern for pattern, code in HINTS if code == "den.w.1")
        self.assertIsNone(re.search(women, "Kvindeligaen: Team Esbjerg-Ikast", re.I))
        self.assertIsNotNone(re.search(women, "A-Liga: AGF-Fortuna Hjørring", re.I))

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript('''CREATE TABLE leagues (
            league_code TEXT PRIMARY KEY,provider TEXT,provider_league_id TEXT,display_name TEXT,
            sport TEXT,import_enabled INT,league_alias TEXT,league_id TEXT,event_type TEXT,
            gracenote_category TEXT,enabled INT);
            CREATE TABLE detection_keywords(category TEXT,keyword TEXT,is_regex INT,target_value TEXT,
            enabled INT,priority INT,description TEXT,UNIQUE(category,keyword));
            INSERT INTO leagues (league_code,provider) VALUES ('den.1','espn');''')

    def tearDown(self):
        self.conn.close()

    def test_merge_is_idempotent_and_preserves_existing(self):
        seed(self.conn)
        seed(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM leagues").fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT provider FROM leagues WHERE league_code='den.1'").fetchone()[0], "espn")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM detection_keywords").fetchone()[0], 2)

    def test_conflict_rolls_back_both_leagues(self):
        self.conn.execute("INSERT INTO leagues (league_code,provider) VALUES ('den.w.1','other')")
        self.conn.commit()
        with self.assertRaises(RuntimeError):
            seed(self.conn)
        self.assertIsNone(self.conn.execute("SELECT * FROM leagues WHERE league_code='den.2'").fetchone())


if __name__ == "__main__":
    unittest.main()
