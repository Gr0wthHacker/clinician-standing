"""``python -m clinician_standing.monitor``: roster load, run, release and digest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from ..api.store import MemoryStore, StandingStore
from .digest import render_digest
from .notify import notifier_from_env
from .run import release_held, run_monitor
from .store import add_roster, connect, load_members_csv


def _store(args: argparse.Namespace) -> StandingStore:
    if args.store_json:
        return MemoryStore.from_dict(json.loads(Path(args.store_json).read_text(encoding="utf-8")))
    import os

    from ..api.store import PostgresStore

    url = os.environ.get("API_DATABASE_URL")
    if not url:
        raise SystemExit("API_DATABASE_URL is not set and no --store-json was given")
    return PostgresStore(url)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clinician-standing-monitor")
    p.add_argument("--db", default="monitor.sqlite", help="monitor SQLite file")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser(
        "roster", help="create a roster and load members from CSV (npi,name,state,credential)"
    )
    r.add_argument("roster_id")
    r.add_argument("org_name")
    r.add_argument("csv")
    r.add_argument("--alert-email")
    run = sub.add_parser("run", help="re-read standing for every rostered NPI and write alerts")
    run.add_argument("--store-json", help="standing data as JSON (tests and dry runs)")
    run.add_argument("--trigger", default="manual", choices=["monthly_ingest", "nursys", "manual"])
    rel = sub.add_parser(
        "release", help="release a held exclusion alert after checking the source record"
    )
    rel.add_argument("alert_id")
    rel.add_argument("--by", required=True)
    d = sub.add_parser("digest", help="write the monthly digest HTML for one roster")
    d.add_argument("roster_id")
    d.add_argument("--from", dest="start", required=True)
    d.add_argument("--to", dest="end", required=True)
    d.add_argument("--store-json")
    d.add_argument("--out", required=True)
    args = p.parse_args(argv)
    conn = connect(args.db)
    now = datetime.now(UTC)
    if args.cmd == "roster":
        add_roster(conn, args.roster_id, args.org_name, now.isoformat(), args.alert_email)
        print(f"{load_members_csv(conn, args.roster_id, args.csv, now.isoformat())} members loaded")
    elif args.cmd == "run":
        res = run_monitor(
            conn, _store(args), now, trigger=args.trigger, notifier=notifier_from_env()
        )
        print(json.dumps(res.__dict__))
    elif args.cmd == "release":
        if not release_held(conn, args.alert_id, args.by):
            print("no held alert with that id", file=sys.stderr)
            return 1
    elif args.cmd == "digest":
        Path(args.out).write_text(
            render_digest(conn, _store(args), args.roster_id, args.start, args.end, now),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
