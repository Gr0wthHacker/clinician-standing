"""python -m clinician_standing.obligations_lite <command> --db obligations.sqlite ...

init                                   create the database
load-rules <rules.csv>                 add verified rule rows
load-roster <roster.csv> --org ID --org-name NAME --start YYYY-MM-DD [--owner NAME]
generate [--as-of YYYY-MM-DD]          rules x roster -> obligations (idempotent)
audit --org ID [--as-of D]             the free roster audit, as text
quote --org ID --rack-pppm CENTS [--as-of D]
file <obligation_id> --submitted D     record a submission
close <filing_id> --approved D --days N --fee CENTS --rule-correct yes|no [--blocker TEXT] [--rework N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .filings import FilingError, close_filing, open_filing
from .generator import generate
from .report import quote, render_audit, roster_audit
from .store import connect, load_roster_csv, load_rules_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m clinician_standing.obligations_lite",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("command")
    p.add_argument("target", nargs="?")
    p.add_argument("--db", default="obligations.sqlite")
    p.add_argument("--as-of", default=date.today().isoformat())
    p.add_argument("--org")
    p.add_argument("--org-name")
    p.add_argument("--start")
    p.add_argument("--owner")
    p.add_argument("--rack-pppm", type=int)
    p.add_argument("--submitted")
    p.add_argument("--approved")
    p.add_argument("--days", type=int)
    p.add_argument("--fee", type=int)
    p.add_argument("--rule-correct", choices=["yes", "no"])
    p.add_argument("--blocker")
    p.add_argument("--rework", type=int, default=0)
    a = p.parse_args(argv)
    conn = connect(a.db)
    try:
        if a.command == "init":
            print(f"initialized {a.db}")
        elif a.command == "load-rules":
            print(f"{load_rules_csv(conn, a.target)} rule rows loaded")
        elif a.command == "load-roster":
            n = load_roster_csv(
                conn,
                a.target,
                org_id=a.org,
                org_name=a.org_name or a.org,
                start_date=a.start or a.as_of,
                default_owner=a.owner,
            )
            print(f"{n} clinicians loaded for {a.org}")
        elif a.command == "generate":
            r = generate(conn, a.as_of)
            print(
                f"{r.written} obligations written, {r.removed} removed, {r.kept_with_filings} kept (filed), "
                f"{r.events} events; by trigger {r.by_trigger}"
            )
        elif a.command == "audit":
            print(render_audit(roster_audit(conn, a.org, a.as_of)))
        elif a.command == "quote":
            print(json.dumps(quote(conn, a.org, a.as_of, rack_pppm_cents=a.rack_pppm), indent=2))
        elif a.command == "file":
            print(f"filing {open_filing(conn, a.target, a.submitted or a.as_of)} opened")
        elif a.command == "close":
            close_filing(
                conn,
                int(a.target),
                approved_at=a.approved or a.as_of,
                actual_processing_days=a.days,
                actual_fee_paid_cents=a.fee,
                rule_was_correct=None if a.rule_correct is None else a.rule_correct == "yes",
                blocker_encountered=a.blocker,
                rework_count=a.rework,
            )
            print(f"filing {a.target} closed")
        else:
            p.error(f"unknown command {a.command}")
    except FilingError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
