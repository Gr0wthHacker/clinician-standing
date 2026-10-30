"""Rules x roster -> dated, priced obligations (Obligations Engine PRD, phase 2, R3).

The generator is stateless and deterministic: it reads the current rule versions and the roster
and rewrites the derived ``obligations`` table. The same input always produces the same rows, and
a rerun changes nothing. Obligations that already have a filing are never touched, because the
filing is history.

Two triggers in v1:

* ``renewal``: the clinician holds the credential in the state. The due date is the board's
  expiry minus the rule's lead days. Expiry is read from the board, never calculated; with no
  board read on file the obligation is ``needs_board_read`` with no due date.
* ``initial``: the roster requires the state and the clinician holds no active credential there.
  Due on the later of the membership start and the run date. Emits a ``new_state`` event.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

__all__ = ["ALERT_DAYS", "GenerateResult", "alert_dates", "generate", "obligation_id"]

#: Expiry calendar triggers (PRD R7): days before the due date an owner is alerted.
ALERT_DAYS = (120, 60, 30, 7)

_OPEN = ("open", "needs_board_read")


def obligation_id(org_id: str, clinician_id: str, rule_key: str) -> str:
    """Deterministic id, so reruns upsert the same row."""
    return hashlib.sha256(f"{org_id}|{clinician_id}|{rule_key}".encode()).hexdigest()[:24]


def alert_dates(due: str | None) -> list[str]:
    """The 120/60/30/7-day alert dates for a due date."""
    if not due:
        return []
    d = date.fromisoformat(due)
    return [(d - timedelta(days=n)).isoformat() for n in ALERT_DAYS]


@dataclass
class GenerateResult:
    as_of: str
    written: int = 0
    removed: int = 0
    kept_with_filings: int = 0
    by_trigger: dict[str, int] = field(default_factory=dict)
    events: int = 0


def _states(raw: str) -> list[str]:
    return sorted({s.strip().upper() for s in raw.split(",") if s.strip()})


def _emit(
    conn: sqlite3.Connection, etype: str, payload: dict[str, object], key: str, at: str
) -> int:
    cur = conn.execute(
        "insert or ignore into events (type, payload, emitted_at, dedupe_key) values (?, ?, ?, ?)",
        (etype, json.dumps(payload, sort_keys=True), at, key),
    )
    return cur.rowcount


def generate(
    conn: sqlite3.Connection, as_of: str, *, generated_at: str | None = None
) -> GenerateResult:
    """Regenerate every obligation implied by the roster and the current rules on ``as_of``."""
    run_day = date.fromisoformat(as_of)
    stamp = generated_at or as_of
    result = GenerateResult(as_of=as_of)
    rules = conn.execute(
        "select rule_key, version, jurisdiction, profession, credential_type, trigger, lead_days,"
        " service_price_cents, government_fee_cents, source_url, last_verified from current_rules"
    ).fetchall()
    members = conn.execute(
        "select m.org_id, m.clinician_id, m.start_date, m.states_required, c.profession,"
        " o.brand, coalesce(o.default_owner, 'unassigned')"
        " from roster_memberships m join clinicians c using (clinician_id) join orgs o using (org_id)"
        " where m.start_date <= ? and (m.end_date is null or m.end_date >= ?)",
        (as_of, as_of),
    ).fetchall()
    held = {
        (r[0], r[1], r[2]): (r[3], r[4])
        for r in conn.execute(
            "select clinician_id, jurisdiction, credential_type, status, expiry_from_board from credentials_held"
        )
    }

    planned: dict[str, tuple[object, ...]] = {}
    for org_id, clinician_id, start, states_raw, profession, brand, owner in members:
        for state in _states(states_raw):
            for rk, ver, juris, prof, ctype, trig, lead, price, gov, src, verified in rules:
                if juris != state or prof != profession:
                    continue
                cred = held.get((clinician_id, state, ctype))
                active = cred is not None and cred[0] == "active"
                if trig == "renewal":
                    if not active:
                        continue
                    expires = cred[1] if cred else None
                    due = (
                        (date.fromisoformat(expires) - timedelta(days=lead)).isoformat()
                        if expires
                        else None
                    )
                    status = "open" if expires else "needs_board_read"
                else:  # initial
                    if active:
                        continue
                    expires = None
                    due = max(date.fromisoformat(start), run_day).isoformat()
                    status = "open"
                    result.events += _emit(
                        conn,
                        "new_state",
                        {
                            "org_id": org_id,
                            "clinician_id": clinician_id,
                            "state": state,
                            "credential_type": ctype,
                        },
                        f"new_state|{org_id}|{clinician_id}|{state}|{ctype}",
                        stamp,
                    )
                if (
                    due
                    and status == "open"
                    and date.fromisoformat(due) - run_day <= timedelta(days=ALERT_DAYS[0])
                ):
                    result.events += _emit(
                        conn,
                        "expiry_window",
                        {
                            "org_id": org_id,
                            "clinician_id": clinician_id,
                            "rule_key": rk,
                            "due_date": due,
                        },
                        f"expiry_window|{org_id}|{clinician_id}|{rk}|{due}",
                        stamp,
                    )
                oid = obligation_id(org_id, clinician_id, rk)
                planned[oid] = (
                    oid,
                    org_id,
                    clinician_id,
                    rk,
                    ver,
                    state,
                    ctype,
                    trig,
                    due,
                    expires,
                    price,
                    gov,
                    owner,
                    status,
                    brand,
                    src,
                    verified,
                    stamp,
                )
                result.by_trigger[trig] = result.by_trigger.get(trig, 0) + 1

    filed = {r[0] for r in conn.execute("select distinct obligation_id from filings")}
    existing = {r[0]: r[1] for r in conn.execute("select obligation_id, status from obligations")}
    for oid, status in existing.items():
        if oid in filed or status not in _OPEN:
            result.kept_with_filings += 1
        elif oid not in planned:
            conn.execute("delete from obligations where obligation_id = ?", (oid,))
            result.removed += 1
    for oid, row in planned.items():
        if oid in filed or existing.get(oid, "open") not in _OPEN:
            continue
        conn.execute(
            "insert into obligations (obligation_id, org_id, clinician_id, rule_key, rule_version, jurisdiction,"
            " credential_type, trigger, due_date, expires_on, price_cents, government_fee_cents, owner, status,"
            " brand, source_url, last_verified, generated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " on conflict (obligation_id) do update set rule_version = excluded.rule_version,"
            " due_date = excluded.due_date, expires_on = excluded.expires_on, price_cents = excluded.price_cents,"
            " government_fee_cents = excluded.government_fee_cents, owner = excluded.owner,"
            " status = excluded.status, source_url = excluded.source_url, last_verified = excluded.last_verified",
            row,
        )
        result.written += 1
    conn.commit()
    return result
