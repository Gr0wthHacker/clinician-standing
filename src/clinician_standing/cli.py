"""Command line interface: ``python -m clinician_standing``.

Five subcommands, each one thing a scheduler or an engineer needs:

* ``ingest <connector_key|all>`` (or ``ingest --all`` / ``ingest --sources a,b``)
  runs connectors and writes ``source_runs``. ``--dry-run`` stops after the
  diff.
* ``status`` prints the last run per source and freshness compliance, which is
  the data behind the Source health screen (PRD section 10) and the
  "source freshness compliance >= 99%" metric (section 11).
* ``init-check`` verifies the database is reachable and the schema is present,
  so a scheduled job fails in one second rather than after a 839 MB download.
* ``engine run`` regenerates the obligation calendar (PRD section 7). Runs
  nightly and on any roster or rule change. ``--dry-run`` reports what it would
  emit without writing.
* ``audit <org_pac_id>`` generates the free roster audit (PRD section 9) from
  data already ingested. Reads only; writes nothing.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg

from .audit import PracticeNotFound, audit_practice, render_html, render_json, render_markdown
from .config import REQUIRED_TABLES, ConfigError, get_settings
from .connectors import CONNECTORS, RunResult, connector_keys, get_connector
from .db import connect, fetch_all, missing_tables
from .engine import run as run_obligations_engine
from .evidence import EvidenceRequired

__all__ = ["build_parser", "main"]

LOGGER = logging.getLogger("clinician_standing")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2

_STATUS_QUERY = """
with latest as (
    select distinct on (source_key)
        source_key, id, started_at, finished_at, status,
        rows_in, rows_changed, rows_new, error, diff_ref
    from source_runs
    order by source_key, started_at desc
),
last_ok as (
    select distinct on (source_key) source_key, finished_at
    from source_runs
    where status = 'ok'
    order by source_key, started_at desc
)
select
    s.key,
    s.display_name,
    s.cadence,
    s.freshness_sla_days,
    s.enabled,
    l.started_at,
    l.finished_at,
    l.status,
    l.rows_in,
    l.rows_changed,
    l.rows_new,
    l.diff_ref,
    l.error,
    o.finished_at as last_success_at,
    case
        when o.finished_at is null then false
        else o.finished_at > now() - make_interval(days => s.freshness_sla_days)
    end as within_sla
from sources s
left join latest l on l.source_key = s.key
left join last_ok o on o.source_key = s.key
order by s.key
"""


def _configure_logging(level: str) -> None:
    """Set up stderr logging at the requested level."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        stream=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m clinician_standing",
        description="Clinician standing ingest layer",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="override LOG_LEVEL (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON instead of a table"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="run one connector or all of them")
    ingest.add_argument(
        "connector",
        metavar="connector_key|all",
        nargs="?",
        default=None,
        help=(
            f"one of: {', '.join(connector_keys())}, 'all', or a comma-separated list. "
            "Defaults to INGEST_SOURCES, or all when that is unset."
        ),
    )
    # --all and --sources are the forms the Makefile and ingest-monthly.yml use.
    # The positional above keeps working; the flags win when both are given.
    selection = ingest.add_mutually_exclusive_group()
    selection.add_argument(
        "--all",
        action="store_true",
        help="run every registered connector (same as the positional 'all')",
    )
    selection.add_argument(
        "--sources",
        metavar="KEYS",
        default=None,
        help="comma-separated connector keys to run, or 'all'",
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "fetch, parse and diff, then stop: no load() and no source_runs row. "
            "The diff summary is still written to STORAGE_PATH."
        ),
    )

    sub.add_parser("status", help="last run per source and freshness compliance")
    sub.add_parser("init-check", help="verify the database is reachable and the schema present")

    # engine: the obligations engine (PRD section 7). Nested subparser because
    # the engine will grow verbs -- `engine explain`, `engine replan <practice>`
    # -- and `engine run` should not have to be renamed when it does.
    engine = sub.add_parser("engine", help="the obligations engine (PRD section 7)")
    engine_sub = engine.add_subparsers(dest="engine_command", required=True)
    engine_run = engine_sub.add_parser(
        "run", help="regenerate the obligation calendar for every active affiliation"
    )
    engine_run.add_argument(
        "--dry-run",
        action="store_true",
        help="plan and report what would be emitted; write nothing",
    )
    engine_run.add_argument(
        "--as-of",
        metavar="YYYY-MM-DD",
        default=None,
        help="run date used for due-date and severity arithmetic (default: today, UTC)",
    )
    engine_run.add_argument(
        "--limit",
        type=int,
        default=25,
        help="rows of the priority-ordered queue to print (default 25; 0 for none)",
    )

    # audit: the free roster audit (PRD section 9). Read-only, and the only
    # input is a group PAC ID, because the point of the artifact is that a
    # prospect supplies nothing.
    audit = sub.add_parser(
        "audit", help="generate the free roster audit for one practice (PRD section 9)"
    )
    audit.add_argument("org_pac_id", metavar="org_pac_id", help="CMS group PAC ID")
    audit.add_argument(
        "--format",
        dest="output_format",
        choices=("json", "markdown", "html"),
        default="markdown",
        help="output format (default markdown). --json is an alias for --format json.",
    )
    audit.add_argument(
        "--as-of",
        metavar="YYYY-MM-DD",
        default=None,
        help="date the due-date arithmetic is computed against (default: today, UTC)",
    )
    audit.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="write to PATH instead of stdout",
    )
    return parser


# --------------------------------------------------------------------- ingest


def _resolve_keys(connector_key: str | None) -> list[str]:
    """Turn the CLI argument into an ordered list of connector keys.

    Accepts a single key, ``all``, or a comma-separated list. When the argument
    is omitted it falls back to ``INGEST_SOURCES``, then to every connector.

    Args:
        connector_key: The raw argument, or None.

    Returns:
        Connector keys in registry order.

    Raises:
        KeyError: If a requested key is not registered.
    """
    if not connector_key:
        requested = list(get_settings().default_sources) or ["all"]
    else:
        requested = [k.strip() for k in connector_key.split(",") if k.strip()]
    if "all" in requested:
        return connector_keys()
    for key in requested:
        get_connector(key)
    # Registry order, not argument order: the DAC file creates the practices and
    # clinicians the other two connectors join to.
    return [k for k in connector_keys() if k in set(requested)]


def _run_ingest(connector_key: str | None, as_json: bool, dry_run: bool = False) -> int:
    """Run one connector, a named subset, or every connector.

    Args:
        connector_key: A registry key, ``all``, a comma-separated list, or None
            to fall back to ``INGEST_SOURCES``.
        as_json: Emit JSON rather than text.
        dry_run: Fetch, parse and diff only; skip ``load()`` and the
            ``source_runs`` write.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    try:
        keys = _resolve_keys(connector_key)
    except KeyError as exc:
        print(str(exc.args[0]), file=sys.stderr)
        return EXIT_CONFIG

    if dry_run:
        LOGGER.warning(
            "DRY RUN: %s will fetch, parse and diff; no load() and no source_runs row",
            ", ".join(keys),
        )

    results: list[dict[str, Any]] = []
    failures = 0
    for key in keys:
        connector = CONNECTORS[key](settings)
        LOGGER.info("starting connector %s", key)
        started = datetime.now(UTC)
        try:
            result = connector.run(dry_run=dry_run)
        except Exception as exc:
            # run() promises never to raise. If it ever does, one bad connector
            # must not end the batch and cost every later source its run.
            LOGGER.exception("connector %s raised out of run()", key)
            result = RunResult(
                source_key=key,
                run_id=connector.run_id,
                started_at=started,
                finished_at=datetime.now(UTC),
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        if result.status not in {"ok", "dry-run"}:
            failures += 1
        duration = (
            (result.finished_at - result.started_at).total_seconds() if result.finished_at else None
        )
        results.append(
            {
                "source_key": result.source_key,
                "dry_run": dry_run,
                "run_id": str(result.run_id),
                "status": result.status,
                "rows_in": result.rows_in,
                "rows_new": result.rows_new,
                "rows_changed": result.rows_changed,
                "diff_ref": result.diff_ref,
                "seconds": round(duration, 1) if duration is not None else None,
                "error": result.error.splitlines()[0] if result.error else None,
            }
        )

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        if dry_run:
            print("DRY RUN -- nothing was loaded and no source_runs row was written")
        for row in results:
            print(
                f"{row['source_key']:<20} {row['status']:<8} "
                f"in={row['rows_in']:>9,} new={row['rows_new']:>9,} "
                f"changed={row['rows_changed']:>9,} {row['seconds']}s"
            )
            if row["error"]:
                print(f"  error: {row['error']}")
    return EXIT_FAILED if failures else EXIT_OK


# --------------------------------------------------------------------- status


def _run_status(as_json: bool) -> int:
    """Print the last run per source and whether it is inside its SLA.

    Returns:
        Process exit code. Non-zero when any enabled source is outside its
        freshness SLA, so a monitor can alert on the exit status alone.
    """
    settings = get_settings()
    with connect(settings) as conn:
        absent = missing_tables(conn, ("sources", "source_runs"))
        if absent:
            print(f"schema incomplete; missing tables: {', '.join(absent)}", file=sys.stderr)
            return EXIT_CONFIG
        rows = fetch_all(conn, _STATUS_QUERY)

    columns = [
        "source_key",
        "display_name",
        "cadence",
        "freshness_sla_days",
        "enabled",
        "started_at",
        "finished_at",
        "status",
        "rows_in",
        "rows_changed",
        "rows_new",
        "diff_ref",
        "error",
        "last_success_at",
        "within_sla",
    ]
    records = [dict(zip(columns, row, strict=False)) for row in rows]
    stale = [r for r in records if r["enabled"] and not r["within_sla"]]

    if as_json:
        compliance = (
            round(1 - len(stale) / len([r for r in records if r["enabled"]]), 4)
            if any(r["enabled"] for r in records)
            else None
        )
        print(
            json.dumps(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "sources": records,
                    "stale_sources": [r["source_key"] for r in stale],
                    "freshness_compliance": compliance,
                },
                indent=2,
                default=str,
            )
        )
    else:
        header = f"{'source':<20} {'last run':<20} {'status':<8} {'rows in':>10} {'changed':>9} {'sla':>5}"
        print(header)
        print("-" * len(header))
        for record in records:
            started = (
                record["started_at"].strftime("%Y-%m-%d %H:%M") if record["started_at"] else "never"
            )
            print(
                f"{record['source_key']:<20} {started:<20} "
                f"{(record['status'] or '-'):<8} "
                f"{(record['rows_in'] or 0):>10,} {(record['rows_changed'] or 0):>9,} "
                f"{('ok' if record['within_sla'] else 'STALE'):>5}"
            )
        if stale:
            print()
            print(
                "stale sources (no successful run inside freshness_sla_days): "
                + ", ".join(r["source_key"] for r in stale)
            )
    return EXIT_FAILED if stale else EXIT_OK


# ----------------------------------------------------------------- init-check


def _run_init_check(as_json: bool) -> int:
    """Verify the database is reachable and the required tables exist.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    report: dict[str, Any] = {"database": "unreachable", "missing_tables": list(REQUIRED_TABLES)}
    try:
        with connect(settings) as conn:
            with conn.cursor() as cur:
                cur.execute("select version()")
                row = cur.fetchone()
            report["database"] = "ok"
            report["server_version"] = row[0] if row else None
            report["missing_tables"] = missing_tables(conn, REQUIRED_TABLES)
            report["registered_sources"] = (
                [r[0] for r in fetch_all(conn, "select key from sources order by key")]
                if not report["missing_tables"]
                else []
            )
    except psycopg.Error as exc:
        report["error"] = str(exc)

    report["storage_path"] = settings.storage_path
    report["storage_is_s3"] = settings.storage_is_s3
    report["connectors"] = connector_keys()
    report["unregistered_connectors"] = [
        k for k in connector_keys() if k not in report.get("registered_sources", [])
    ]

    healthy = report["database"] == "ok" and not report["missing_tables"]
    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"database:      {report['database']}")
        if report.get("error"):
            print(f"error:         {report['error']}")
        if report.get("server_version"):
            print(f"server:        {report['server_version']}")
        print(f"storage:       {report['storage_path']}")
        if report["missing_tables"]:
            print(f"MISSING TABLES: {', '.join(report['missing_tables'])}")
        else:
            print("schema:        all required tables present")
        if report["unregistered_connectors"]:
            print(
                "sources registry does not yet list: "
                + ", ".join(report["unregistered_connectors"])
                + " (the first run of each registers itself)"
            )
    return EXIT_OK if healthy else EXIT_FAILED


# ----------------------------------------------------------------------- engine


def _run_engine(as_of_raw: str | None, as_json: bool, dry_run: bool, limit: int) -> int:
    """Regenerate the obligation calendar (PRD section 7).

    Args:
        as_of_raw: ``YYYY-MM-DD`` run date, or None for today in UTC.
        as_json: Emit JSON rather than a table.
        dry_run: Plan and report; write nothing.
        limit: How many priority-ordered rows to print.

    Returns:
        Process exit code.
    """
    try:
        as_of = date.fromisoformat(as_of_raw) if as_of_raw else None
    except ValueError:
        print(f"--as-of must be YYYY-MM-DD, got {as_of_raw!r}", file=sys.stderr)
        return EXIT_CONFIG

    settings = get_settings()
    with connect(settings) as conn:
        absent = missing_tables(conn, ("obligations", "requirements", "affiliations", "licenses"))
        if absent:
            print(f"schema incomplete; missing tables: {', '.join(absent)}", file=sys.stderr)
            return EXIT_CONFIG
        result = run_obligations_engine(conn, as_of=as_of, dry_run=dry_run)
        if not dry_run:
            conn.commit()

    summary = result.summary()
    if as_json:
        summary["queue"] = [
            {
                "clinician_id": str(spec.clinician_id),
                "practice_id": str(spec.practice_id),
                "obligation_type": spec.obligation_type,
                "state": spec.state,
                "payer": spec.payer,
                "due_date": spec.due_date.isoformat(),
                "window_opens": spec.window_opens.isoformat() if spec.window_opens else None,
                "severity": spec.severity,
                "rule_version": spec.rule_version,
                "reason": spec.reason,
            }
            for spec in (result.planned[:limit] if limit else [])
        ]
        print(json.dumps(summary, indent=2, default=str))
        return EXIT_OK

    if dry_run:
        print("DRY RUN -- nothing was written")
    print(f"as of:         {summary['as_of']}")
    print(
        f"planned:       {summary['planned']}  "
        f"({'would insert' if dry_run else 'inserted'} {summary['inserted']}, "
        f"{'would update' if dry_run else 'updated'} {summary['updated']}, "
        f"unchanged {summary['unchanged']})"
    )
    for obligation_type, count in summary["by_type"].items():
        print(f"  {obligation_type:<26} {count:>6,}")
    print(
        "severity:      "
        + "  ".join(f"{name}={count:,}" for name, count in summary["by_severity"].items())
    )
    if limit:
        print()
        header = (
            f"{'severity':<9} {'due':<11} {'type':<24} {'st':<3} {'payer':<10} {'ver':>3}  reason"
        )
        print(header)
        print("-" * len(header))
        for spec in result.planned[:limit]:
            print(
                f"{spec.severity:<9} {spec.due_date.isoformat():<11} "
                f"{spec.obligation_type:<24} {(spec.state or '-'):<3} "
                f"{(spec.payer or '-'):<10} "
                f"{(spec.rule_version if spec.rule_version is not None else '-'):>3}  "
                f"{spec.reason}"
            )
    return EXIT_OK


# ---------------------------------------------------------------------- audit


def _run_audit(
    org_pac_id: str,
    output_format: str,
    as_of: str | None,
    output_path: str | None,
) -> int:
    """Generate the free roster audit for one practice and write it out.

    Args:
        org_pac_id: CMS group PAC ID.
        output_format: ``json``, ``markdown`` or ``html``.
        as_of: Optional ``YYYY-MM-DD`` the due-date arithmetic runs against.
        output_path: File to write, or None for stdout.

    Returns:
        Process exit code. ``EXIT_FAILED`` when the practice is not in the
        database, because an audit of a practice that was never ingested is a
        failed run, not an empty one.
    """
    try:
        effective = date.fromisoformat(as_of) if as_of else None
    except ValueError:
        print(f"--as-of must be YYYY-MM-DD, got {as_of!r}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        result = audit_practice(org_pac_id, as_of=effective)
    except PracticeNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAILED

    renderer = {
        "json": render_json,
        "markdown": render_markdown,
        "html": render_html,
    }[output_format]
    document = renderer(result)

    if output_path:
        Path(output_path).write_text(document, encoding="utf-8")
        LOGGER.info(
            "wrote %s audit for %s to %s (%s findings, worst: %s)",
            output_format,
            org_pac_id,
            output_path,
            len(result.findings),
            result.worst_severity.value,
        )
    else:
        print(document)
    return EXIT_OK


# ----------------------------------------------------------------------- main


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument vector; ``sys.argv[1:]`` when omitted.

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    settings = get_settings()
    _configure_logging(args.log_level or settings.log_level)

    try:
        settings.validate()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        if args.command == "ingest":
            # --sources and --all are mutually exclusive in the parser; either
            # one overrides the positional so the workflow and the Makefile can
            # keep using flags while `ingest oig_leie` still works.
            selection = args.sources or ("all" if args.all else args.connector)
            return _run_ingest(selection, args.json, dry_run=args.dry_run)
        if args.command == "status":
            return _run_status(args.json)
        if args.command == "init-check":
            return _run_init_check(args.json)
        if args.command == "engine" and args.engine_command == "run":
            return _run_engine(args.as_of, args.json, args.dry_run, args.limit)
        if args.command == "audit":
            # The global --json flag predates --format; honour it as an alias
            # rather than making the two disagree silently.
            fmt = "json" if args.json else args.output_format
            return _run_audit(args.org_pac_id, fmt, args.as_of, args.output)
    except (psycopg.Error, ConfigError, EvidenceRequired) as exc:
        LOGGER.error("%s: %s", type(exc).__name__, exc)
        return EXIT_FAILED
    print(f"unknown command {args.command!r}", file=sys.stderr)
    return EXIT_CONFIG
