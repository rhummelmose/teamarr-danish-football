"""Read-only smoke test: python -m teamarr_danish --league aliga --date YYYY-MM-DD."""

import argparse
from dataclasses import asdict
from datetime import date
import json

from .aliga import ALigaClient
from .betinia import BetiniaClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", choices=["betinia", "aliga"], required=True)
    parser.add_argument("--date", type=date.fromisoformat)
    args = parser.parse_args()
    client = BetiniaClient() if args.league == "betinia" else ALigaClient()
    fixtures = client.events(args.date) if args.date else client.fixtures()
    print(json.dumps([asdict(f) for f in fixtures], ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
