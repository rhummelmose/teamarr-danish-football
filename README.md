# Teamarr Danish Football

Free fixture providers for **Betinia Ligaen** (Danish men's second tier) and
**A-Ligaen** (Danish women's top tier). No TheSportsDB subscription, personal API
key, account, or video-stream credentials are required.

| Provider | Teamarr league | Official source |
|---|---|---|
| `betinia` | `den.2` | [1-division.dk/kampprogram](https://1-division.dk/kampprogram) and its public website widget API |
| `aliga` | `den.w.1` | [a-liga.dk/kampe](https://www.a-liga.dk/kampe/) — DBU-backed HTML schedule |

This supplies **fixture metadata, not video**. Teamarr still needs a legitimate
matching stream, an active league subscription, and an event template to create
a channel. It does not turn a league fixture into a playable stream on its own.

## Status and compatibility

Tested against **Teamarr 2.26.0**, upstream commit
`22ce5d74c6a2eb1ec55a02341e098490888d5743`. Teamarr does not currently expose a
runtime provider plugin loader, so installation uses its documented registry
interface plus a small generated registry overlay. No matcher modifications,
paid-feature bypass, or replacement of ESPN/TheSportsDB is involved.

This is an independent, unofficial integration. Source websites and Teamarr may
change. **Rebuild/review the registry overlay before upgrading Teamarr**; do not
mount a 2.26.0 registry over a newer release.

## Read-only use

Requires Python 3.11+ and system timezone data. The standalone clients and CLI use
only the Python standard library; importing the Teamarr adapter requires Teamarr.

```sh
python -m teamarr_danish --league betinia
python -m teamarr_danish --league aliga --date 2026-11-21
python -m unittest discover -s tests -v
```

Run the tests inside a Teamarr environment as well to exercise its real
`SportsProvider`, `Team`, and `Event` interfaces. No live network is used by tests;
the CLI performs the explicit live source checks.

## Install in Docker

Back up your existing configuration first. Keep the existing Teamarr image,
networks, mounts, environment, and any other patches. Pause scheduled generation
and wait for a running generation to finish while changing provider registration.

1. Clone this repository beside your Compose configuration, for example into
   `./connectors/teamarr-danish-football`.
2. Copy it temporarily into the **existing pinned container** and generate the
   registry overlay from that container's original file (not an arbitrary newer
   checkout):

   ```sh
   docker cp ./connectors/teamarr-danish-football teamarr:/tmp/danish-football
   docker exec -e PYTHONPATH=/tmp/danish-football:/app teamarr \
     python -m teamarr_danish.install \
     --registry-output /tmp/danish-providers-init.py \
     --database /app/data/teamarr.db
   mkdir -p ./connectors/teamarr-danish-football/overlay
   docker cp teamarr:/tmp/danish-providers-init.py \
     ./connectors/teamarr-danish-football/overlay/providers_init.py
   ```

   The installer creates an owner-only SQLite backup, adds only the two league
   definitions and narrowly scoped league-name hints, and refuses conflicting
   existing provider ownership. It is idempotent. It **does not** enable sports
   subscriptions, change sources/templates, or create/delete channels.

3. **Append**, do not replace, these volume entries for the Teamarr service:

   ```yaml
   volumes:
     - ./connectors/teamarr-danish-football/teamarr_danish:/app/teamarr_danish:ro
     - ./connectors/teamarr-danish-football/overlay/providers_init.py:/app/teamarr/providers/__init__.py:ro
   ```

4. Recreate only Teamarr. Refresh its team/league cache. Select **Betinia Ligaen**
   and **A-Ligaen** in Subscriptions and assign your Soccer Club event template.
   Resume the previous generation schedule.
5. Preview your relevant sources before generating. Provider labels that use
   `A-Liga: Home-Away` may need source-specific team extraction. For example,
   append `A[- ]Liga(?:en)?` to an existing competition-name alternation; do not
   overwrite unrelated extraction rules. Betinia labels often use
   `Home - Away | Betinia LIGA`. Keep the source's actual timezone/date format.

Do not map bare **Kvindeligaen** to women's football: Danish providers also use
that label for women's handball. Men and women have different league/provider
identities even when club names (AGF, Kolding, etc.) coincide.

### Rollback

Disable just these two subscriptions, then remove these two mounts and recreate
Teamarr. Remove the two definitions/hints only after reviewing dependent managed
channels. Do not restore an old full database or Dispatcharr lineup over later
edits. No other provider or regular channel needs to change.

## Data behavior and limits

- The current season/pool is discovered dynamically; no season-specific ID is
  hardcoded. Betinia supports historical seasons advertised by its site. A-Liga
  exposes only phases currently published on its programme page.
- Official match IDs survive kickoff changes. A-Liga IDs include season year.
- Kickoffs are UTC-aware. Danish page times use `Europe/Copenhagen`, including
  daylight-saving time. Date-only kickoffs are explicitly `time_tbd`; ambiguous
  DST times and unknown records are rejected, not guessed.
- A-Liga does not publish an unambiguous live/final flag on its schedule page.
  A listed score becomes `final` only four hours after kickoff; prior to that it
  is `live`. A past kickoff without a score is **not** assumed completed.
  This connector is not a real-time score service.
- Schedules are cached for 15 minutes, Betinia season metadata for one hour and
  public widget configuration for six hours. Concurrent calls share downloads.
  Requests have 20-second timeouts and an 8 MiB response limit. Failures back off
  for 60 seconds; stale schedules are not silently presented as fresh.
- Teamarr also has its own outer event cache. Its normal cache lifetimes still
  apply; a 15-minute generation interval does not promise 15-minute fixture
  freshness. The connectors do not change global cache policy.
- The existing Game Thumbs templates may use generic fallback artwork for these
  leagues. To use a verified club badge instead, a league-specific template can
  set its logo to `{home_team_logo}`. The connectors expose both teams' badges.
- Teamarr integration uses its native HTTP client policy (including configured
  proxy and user agent). Standalone use follows standard urllib proxy settings.
- Betinia's **public embed token** is discovered from its website at runtime;
  it is neither hardcoded nor logged. It is not a subscriber credential.
- Club badges link to the source's own image hosts. Artwork belongs to its
  respective owners; it is not bundled or licensed by this repository.
- Source errors/schema changes are reported in logs. Test fixtures are small,
  synthetic HTML/JSON examples; production schedules and private app data are
  not committed.

## Development

Run `python -m unittest discover -s tests -v`. CI also loads the pinned Teamarr
core for adapter contract tests. Tests cover dates/DST, UTC midnight, postponed
and cancelled fixtures, stable IDs, identity scoping, malformed source pages,
cache expiry/failure recovery, and transactional/idempotent database seeding.

License: AGPL-3.0-only, compatible with Teamarr. No affiliation with Teamarr,
Divisionsforeningen, DBU, Ligaforbundet, or the broadcasters.
