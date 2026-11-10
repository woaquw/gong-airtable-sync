#!/usr/bin/env python3
"""Sync Gong call data (metadata, participants, summary, transcript) into Airtable.

Examples:
    python sync.py --mock --dry-run            # demo, no API keys needed, writes CSV
    python sync.py --mock                      # sample calls -> your Airtable table
    python sync.py --from 2026-11-01 --to 2026-11-08
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airtable_client import AirtableClient, AirtableError
from gong_client import GongClient, GongError, MockGongClient
from transform import FIELDS, call_to_fields


def load_env(path):
    """Read KEY=VALUE lines from .env into os.environ (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def to_iso(day, end_of_day=False):
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        dt += timedelta(days=1) - timedelta(seconds=1)
    return dt.isoformat().replace("+00:00", "Z")


def require(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    return [os.environ[n] for n in names]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    load_env(Path(__file__).parent / ".env")

    today = datetime.now(timezone.utc).date()
    p = argparse.ArgumentParser(description="Sync Gong calls into Airtable.")
    p.add_argument("--mock", action="store_true", help="use sample data instead of the Gong API")
    p.add_argument("--from", dest="from_day", default=str(today - timedelta(days=7)),
                   help="start date YYYY-MM-DD (default: 7 days ago)")
    p.add_argument("--to", dest="to_day", default=str(today), help="end date YYYY-MM-DD (default: today)")
    p.add_argument("--limit", type=int, help="only process the first N calls (handy for a test batch)")
    p.add_argument("--no-transcripts", action="store_true", help="skip transcripts")
    p.add_argument("--dry-run", action="store_true", help="do not write to Airtable, only to CSV")
    p.add_argument("--csv", default="output.csv", help="CSV path for --dry-run (default: output.csv)")
    p.add_argument("--setup", action="store_true",
                   help="create the Airtable table with all fields if it does not exist yet")
    args = p.parse_args()

    if args.mock:
        gong = MockGongClient()
        print("Source: sample data (mock mode)")
    else:
        key, secret = require("GONG_ACCESS_KEY", "GONG_ACCESS_SECRET")
        gong = GongClient(key, secret, os.environ.get("GONG_BASE_URL", "https://api.gong.io"))
        print(f"Source: Gong API, {args.from_day} .. {args.to_day}")

    try:
        calls = list(gong.iter_calls(to_iso(args.from_day), to_iso(args.to_day, end_of_day=True)))
        if args.limit:
            calls = calls[:args.limit]
        print(f"Calls found: {len(calls)}")

        transcripts = {}
        if calls and not args.no_transcripts:
            ids = [str(c["metaData"]["id"]) for c in calls]
            transcripts = gong.get_transcripts(ids)
            print(f"Transcripts fetched: {len(transcripts)}")
    except GongError as e:
        sys.exit(str(e))

    rows = [call_to_fields(c, transcripts.get(str(c["metaData"]["id"]))) for c in calls]

    if args.dry_run:
        write_csv(rows, args.csv)
        print(f"Dry run: {len(rows)} rows written to {args.csv}")
        return

    token, base_id = require("AIRTABLE_TOKEN", "AIRTABLE_BASE_ID")
    table = os.environ.get("AIRTABLE_TABLE", "Calls")
    airtable = AirtableClient(token, base_id, table)
    try:
        if args.setup:
            made = airtable.ensure_table()
            print(f"Airtable table '{table}': {'created' if made else 'already exists'}")
        created, updated = airtable.upsert(rows)
    except AirtableError as e:
        sys.exit(str(e))
    print(f"Airtable '{table}': {created} created, {updated} updated")


if __name__ == "__main__":
    main()
