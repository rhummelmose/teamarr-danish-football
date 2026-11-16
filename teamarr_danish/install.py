"""Explicit, version-guarded installation helpers. Never modifies subscriptions.

Run inside Teamarr's container (after mounting the package), with --database to
seed ONLY our two league rows and matching hints. --registry-output creates a
mountable copy, leaving the original registry untouched. Review before mounting.
"""

import argparse
import hashlib
import os
from pathlib import Path
import sqlite3
from datetime import UTC, datetime

MARKER = "# teamarr-danish-football registry hook v1"
HOOK = "\n" + MARKER + "\nfrom teamarr_danish.registration import register as _register_danish\n_register_danish()\n"
LEAGUES = [
    ("den.2", "betinia", "85", "Betinia Ligaen", "betinia-ligaen"),
    ("den.w.1", "aliga", "4", "A-Ligaen", "a-ligaen"),
]
HINTS = [
    (r"\b(?:Betinia(?:\s+Liga(?:en)?)?|NordicBet\s+Liga(?:en)?)\b", "den.2"),
    (r"\b(?:A[- ]Liga(?:en)?|Gjensidige\s+Kvindeliga(?:en)?)\b", "den.w.1"),
]


def seed(conn):
    """Transactional, idempotent inserts; reject ownership conflicts."""
    with conn:
        for code, provider, ident, display, slug in LEAGUES:
            old = conn.execute("SELECT provider FROM leagues WHERE league_code=?", (code,)).fetchone()
            if old and old[0] != provider:
                raise RuntimeError(f"League {code} already belongs to another provider")
            conn.execute("""INSERT OR IGNORE INTO leagues
                (league_code,provider,provider_league_id,display_name,sport,import_enabled,
                 league_alias,league_id,event_type,gracenote_category,enabled)
                VALUES (?,?,?,?,'soccer',1,?,?,'team_vs_team','Soccer',1)""",
                         (code, provider, ident, display, display, slug))
        for pattern, code in HINTS:
            old = conn.execute("SELECT target_value FROM detection_keywords WHERE category='league_hints' AND keyword=?", (pattern,)).fetchone()
            if old and old[0] != code:
                raise RuntimeError("A league detection rule already has a different target")
            conn.execute("""INSERT OR IGNORE INTO detection_keywords
                (category,keyword,is_regex,target_value,enabled,priority,description)
                VALUES ('league_hints',?,1,?,1,100,'Official Danish football fixture provider')""",
                         (pattern, code))


def registry_overlay(source, output):
    root = source.parents[2]
    version = (root / "pyproject.toml").read_text()
    if 'version = "2.26.0"' not in version:
        raise RuntimeError("Only Teamarr 2.26.0 is verified; review compatibility before upgrading")
    body = source.read_text()
    if MARKER not in body:
        body += HOOK
    compile(body, str(output), "exec")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body)
    print("Registry overlay written; source SHA256:", hashlib.sha256(source.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teamarr-root", type=Path, default=Path("/app"))
    parser.add_argument("--registry-output", type=Path)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    if args.registry_output:
        registry_overlay(args.teamarr_root / "teamarr/providers/__init__.py", args.registry_output)
    if args.database:
        if not args.database.is_file():
            parser.error("Existing Teamarr database is required")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = args.database.with_name(args.database.name + f".before-danish-{stamp}")
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(args.database, timeout=30) as conn:
            with sqlite3.connect(backup) as target:
                conn.backup(target)
            seed(conn)
        print("Backed up database; seeded only Danish league definitions and hints")
    if not args.registry_output and not args.database:
        parser.error("Specify --registry-output and/or --database")


if __name__ == "__main__":
    main()
