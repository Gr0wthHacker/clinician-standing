"""SQLite connection, schema and CSV loaders for the rules table and a roster (PRD R1, R2)."""

from __future__ import annotations

import csv
import sqlite3
from importlib.resources import files
from pathlib import Path

__all__ = ["RULE_COLUMNS", "connect", "load_roster_csv", "load_rules_csv"]

RULE_COLUMNS = (
    "rule_key",
    "version",
    "jurisdiction",
    "profession",
    "credential_type",
    "trigger",
    "lead_days",
    "service_price_cents",
    "government_fee_cents",
    "cycle_months",
    "prerequisites",
    "form",
    "delegation_mechanism",
    "source_url",
    "last_verified",
    "verified_by",
    "second_verifier",
    "effective_date",
    "change_source",
)
_INTS = {"version", "lead_days", "service_price_cents", "government_fee_cents", "cycle_months"}


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open (and create) the database with foreign keys on and the schema applied."""
    conn = sqlite3.connect(str(path))
    conn.execute("pragma foreign_keys = on")
    conn.executescript(files(__package__).joinpath("schema.sql").read_text(encoding="utf-8"))
    return conn


def _blank_to_none(v: str | None) -> str | None:
    return None if v is None or not v.strip() else v.strip()


def load_rules_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    """Insert rule rows. A blank fee stays null ("not published"); it is never filled in."""
    n = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            values = []
            for col in RULE_COLUMNS:
                v = _blank_to_none(row.get(col))
                values.append(int(v) if v is not None and col in _INTS else v)
            if values[1] is None:
                values[1] = 1
            if values[6] is None:
                values[6] = 60
            conn.execute(
                f"insert into rules ({', '.join(RULE_COLUMNS)}) values ({', '.join('?' * len(RULE_COLUMNS))})",
                values,
            )
            n += 1
    conn.commit()
    return n


def load_roster_csv(
    conn: sqlite3.Connection,
    path: str | Path,
    *,
    org_id: str,
    org_name: str,
    start_date: str,
    default_owner: str | None = None,
    brand: str = "clinician-standing",
) -> int:
    """Load a roster CSV: npi, name, profession, specialty, states_required, and optionally
    held_states with expiry_<STATE> columns read from the board.

    ``held_states`` lists states where the clinician holds an active license; each may carry an
    ``expiry_<STATE>`` date taken from the board record. No expiry is ever computed here.
    """
    conn.execute(
        "insert into orgs (org_id, name, brand, default_owner) values (?, ?, ?, ?)"
        " on conflict (org_id) do update set name = excluded.name, default_owner = excluded.default_owner",
        (org_id, org_name, brand, default_owner),
    )
    n = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            npi = _blank_to_none(row.get("npi"))
            cid = npi or row["name"].strip().lower().replace(" ", "-")
            conn.execute(
                "insert into clinicians (clinician_id, npi, name, profession, specialty) values (?, ?, ?, ?, ?)"
                " on conflict (clinician_id) do update set name = excluded.name, profession = excluded.profession",
                (
                    cid,
                    npi,
                    row["name"].strip(),
                    row["profession"].strip().upper(),
                    _blank_to_none(row.get("specialty")),
                ),
            )
            conn.execute(
                "insert into roster_memberships (org_id, clinician_id, start_date, states_required) values (?, ?, ?, ?)"
                " on conflict (org_id, clinician_id) do update set states_required = excluded.states_required",
                (org_id, cid, start_date, row.get("states_required", "")),
            )
            for state in [
                s.strip().upper() for s in (row.get("held_states") or "").split(",") if s.strip()
            ]:
                expiry = _blank_to_none(row.get(f"expiry_{state}"))
                conn.execute(
                    "insert into credentials_held (clinician_id, jurisdiction, credential_type, status, expiry_from_board,"
                    " board_read_at) values (?, ?, 'license', 'active', ?, ?)"
                    " on conflict (clinician_id, jurisdiction, credential_type) do update set expiry_from_board = excluded.expiry_from_board,"
                    " board_read_at = excluded.board_read_at",
                    (cid, state, expiry, _blank_to_none(row.get("board_read_at"))),
                )
            n += 1
    conn.commit()
    return n
