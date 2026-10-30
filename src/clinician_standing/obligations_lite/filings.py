"""Filing write-back (T909, PRD R6). Every filing records what happened, from filing one:
``actual_processing_days``, ``actual_fee_paid``, ``rule_was_correct``, ``blocker_encountered``.
No filing closes without the processing days and the fee paid; the schema enforces the same rule,
so a direct SQL update cannot skip it either. A filing that says the rule was wrong opens a
rule-review ticket through a trigger."""

from __future__ import annotations

import sqlite3
from datetime import date

__all__ = ["FilingError", "close_filing", "open_filing"]


class FilingError(ValueError):
    """A filing write that the write-back rules refuse."""


def open_filing(conn: sqlite3.Connection, obligation_id: str, submitted_at: str) -> int:
    """Record a submission against an obligation and stamp the rule version it was filed under."""
    row = conn.execute(
        "select rule_key, rule_version, status from obligations where obligation_id = ?",
        (obligation_id,),
    ).fetchone()
    if row is None:
        raise FilingError(f"no obligation {obligation_id}")
    if row[2] == "needs_board_read":
        raise FilingError("read the expiry from the board before filing")
    date.fromisoformat(submitted_at)
    cur = conn.execute(
        "insert into filings (obligation_id, rule_key, rule_version, submitted_at) values (?, ?, ?, ?)",
        (obligation_id, row[0], row[1], submitted_at),
    )
    conn.execute(
        "update obligations set status = 'filed' where obligation_id = ?", (obligation_id,)
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def close_filing(
    conn: sqlite3.Connection,
    filing_id: int,
    *,
    approved_at: str,
    actual_processing_days: int | None,
    actual_fee_paid_cents: int | None,
    rule_was_correct: bool | None,
    blocker_encountered: str | None = None,
    rework_count: int = 0,
) -> None:
    """Close a filing with its write-back fields. Refuses a close missing any required field."""
    missing = [
        name
        for name, v in (
            ("actual_processing_days", actual_processing_days),
            ("actual_fee_paid", actual_fee_paid_cents),
            ("rule_was_correct", rule_was_correct),
        )
        if v is None
    ]
    if missing:
        raise FilingError(f"a filing cannot close without {', '.join(missing)}")
    if rule_was_correct is False and not (blocker_encountered or "").strip():
        raise FilingError(
            "say what was wrong in blocker_encountered when rule_was_correct is false"
        )
    date.fromisoformat(approved_at)
    row = conn.execute(
        "select obligation_id, closed_at from filings where filing_id = ?", (filing_id,)
    ).fetchone()
    if row is None:
        raise FilingError(f"no filing {filing_id}")
    if row[1] is not None:
        raise FilingError(f"filing {filing_id} is already closed")
    conn.execute(
        "update filings set approved_at = ?, actual_processing_days = ?, actual_fee_paid_cents = ?,"
        " rule_was_correct = ?, blocker_encountered = ?, rework_count = ?, closed_at = ? where filing_id = ?",
        (
            approved_at,
            actual_processing_days,
            actual_fee_paid_cents,
            int(bool(rule_was_correct)),
            blocker_encountered,
            rework_count,
            approved_at,
            filing_id,
        ),
    )
    conn.execute("update obligations set status = 'closed' where obligation_id = ?", (row[0],))
    conn.commit()
