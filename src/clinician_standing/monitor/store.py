"""SQLite store for rosters, snapshots and alerts."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..api.models import is_valid_npi
from .diff import Alert

__all__ = ["active_npis", "add_roster", "connect", "load_members_csv", "write_alert"]

#: Roster CSV columns. Anything else in the file is refused, so a date of birth or an email
#: column cannot ride along into the database.
MEMBER_COLUMNS = ("npi", "name", "state", "credential")


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.executescript(files(__package__).joinpath("schema.sql").read_text(encoding="utf-8"))
    return conn


def add_roster(
    conn: sqlite3.Connection,
    roster_id: str,
    org_name: str,
    now: str,
    alert_email: str | None = None,
) -> None:
    conn.execute(
        "insert into monitor_rosters (roster_id, org_name, alert_email, created_at) values (?, ?, ?, ?)"
        " on conflict (roster_id) do update set org_name = excluded.org_name,"
        " alert_email = coalesce(excluded.alert_email, monitor_rosters.alert_email)",
        (roster_id, org_name, alert_email, now),
    )
    conn.commit()


def load_members_csv(conn: sqlite3.Connection, roster_id: str, path: str | Path, now: str) -> int:
    n = 0
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        extra = set(reader.fieldnames or ()) - set(MEMBER_COLUMNS)
        if extra:
            raise ValueError(f"roster CSV has columns the monitor does not accept: {sorted(extra)}")
        for row in reader:
            npi = (row.get("npi") or "").strip()
            if not is_valid_npi(npi):
                raise ValueError(f"invalid NPI on roster: {npi!r}")
            state = (row.get("state") or "").strip().upper() or None
            conn.execute(
                "insert into monitor_roster_members (roster_id, npi, name, state, credential, added_at)"
                " values (?, ?, ?, ?, ?, ?) on conflict (roster_id, npi) do update set"
                " name = excluded.name, state = excluded.state, credential = excluded.credential,"
                " removed_at = null",
                (
                    roster_id,
                    npi,
                    (row.get("name") or "").strip() or None,
                    state,
                    (row.get("credential") or "").strip() or None,
                    now,
                ),
            )
            n += 1
    conn.commit()
    return n


def active_npis(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """NPI -> roster ids, across every active roster."""
    out: dict[str, list[str]] = {}
    for r in conn.execute(
        "select m.npi, m.roster_id from monitor_roster_members m"
        " join monitor_rosters r using (roster_id)"
        " where r.status = 'active' and m.removed_at is null order by m.npi, m.roster_id"
    ):
        out.setdefault(r["npi"], []).append(r["roster_id"])
    return out


def write_alert(
    conn: sqlite3.Connection, roster_id: str, alert: Alert, now: str, source_as_of: str | None
) -> bool:
    """Insert one alert; returns False when the same alert already exists for the roster.

    A new open exclusion is written as ``held``: it waits for a person to confirm it against the
    source record before any email goes out (a wrong exclusion alert does more harm than a delay).
    """
    alert_id = hashlib.sha256(f"{roster_id}|{alert.dedupe}".encode()).hexdigest()[:32]
    status = "held" if alert.kind == "exclusion_new" else "pending"
    detail: dict[str, Any] = {
        "message": alert.message,
        "before": alert.before,
        "after": alert.after,
    }
    cur = conn.execute(
        "insert or ignore into monitor_alerts (alert_id, roster_id, npi, kind, delivery, status, detail,"
        " source_key, source_as_of, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            alert_id,
            roster_id,
            alert.npi,
            alert.kind,
            alert.delivery,
            status,
            json.dumps(detail, sort_keys=True),
            alert.source_key,
            source_as_of,
            now,
        ),
    )
    return cur.rowcount == 1
