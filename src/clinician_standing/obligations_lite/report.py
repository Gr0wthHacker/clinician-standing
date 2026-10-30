"""The free roster audit (PRD R4) and the quote (R5), both read straight from obligations.

The audit names missing states, upcoming expiries and the cost of the current gaps, with the rule's
source and last-verified date on every line (PRD guardrail: rule provenance on every output).
Government fees are shown as pass-through and kept apart from service fees; a fee the board does
not publish is shown as "not published", never estimated.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..pricing import DiscountTier, discount_percent_for, effective_unit_price_cents

__all__ = ["AuditLine", "RosterAudit", "quote", "render_audit", "roster_audit"]


@dataclass
class AuditLine:
    clinician: str
    npi: str | None
    jurisdiction: str
    credential_type: str
    trigger: str
    due_date: str | None
    expires_on: str | None
    status: str
    price_cents: int
    government_fee_cents: int | None
    source_url: str
    last_verified: str


@dataclass
class RosterAudit:
    org_name: str
    as_of: str
    clinicians: int
    missing_states: list[AuditLine] = field(default_factory=list)
    upcoming: list[AuditLine] = field(default_factory=list)
    needs_board_read: list[AuditLine] = field(default_factory=list)

    @property
    def gap_service_cents(self) -> int:
        return sum(x.price_cents for x in self.missing_states + self.upcoming)

    @property
    def gap_government_cents(self) -> int:
        return sum(x.government_fee_cents or 0 for x in self.missing_states + self.upcoming)

    @property
    def unpublished_fees(self) -> int:
        return sum(1 for x in self.missing_states + self.upcoming if x.government_fee_cents is None)


def _lines(conn: sqlite3.Connection, org_id: str) -> list[AuditLine]:
    rows = conn.execute(
        "select c.name, c.npi, o.jurisdiction, o.credential_type, o.trigger, o.due_date, o.expires_on, o.status,"
        " o.price_cents, o.government_fee_cents, o.source_url, o.last_verified"
        " from obligations o join clinicians c using (clinician_id) where o.org_id = ?"
        " order by coalesce(o.due_date, '9999'), c.name, o.jurisdiction",
        (org_id,),
    ).fetchall()
    return [AuditLine(*r) for r in rows]


def roster_audit(
    conn: sqlite3.Connection, org_id: str, as_of: str, window_days: int = 120
) -> RosterAudit:
    org = conn.execute("select name from orgs where org_id = ?", (org_id,)).fetchone()
    if org is None:
        raise KeyError(org_id)
    n = conn.execute(
        "select count(*) from roster_memberships where org_id = ?", (org_id,)
    ).fetchone()[0]
    horizon = (date.fromisoformat(as_of) + timedelta(days=window_days)).isoformat()
    audit = RosterAudit(org_name=org[0], as_of=as_of, clinicians=n)
    for line in _lines(conn, org_id):
        if line.status not in ("open", "needs_board_read"):
            continue
        if line.trigger == "initial":
            audit.missing_states.append(line)
        elif line.status == "needs_board_read":
            audit.needs_board_read.append(line)
        elif line.due_date and line.due_date <= horizon:
            audit.upcoming.append(line)
    return audit


def _usd(cents: int | None) -> str:
    return "not published" if cents is None else f"${cents / 100:,.2f}"


def render_audit(a: RosterAudit) -> str:
    """Plain-text audit for human review before it goes out (PRD R4: under 2 hours of review)."""
    out = [
        f"Roster audit: {a.org_name}",
        f"As of {a.as_of}. {a.clinicians} clinicians on the roster.",
        "",
        f"States the roster requires with no active license on file: {len(a.missing_states)}",
    ]
    for x in a.missing_states:
        out.append(
            f"  {x.clinician} ({x.npi or 'no NPI'}): {x.jurisdiction} {x.credential_type}. Service {_usd(x.price_cents)},"
            f" state fee {_usd(x.government_fee_cents)}. Rule: {x.source_url} (verified {x.last_verified})"
        )
    out += ["", f"Renewals due in the next 120 days: {len(a.upcoming)}"]
    for x in a.upcoming:
        out.append(
            f"  {x.clinician}: {x.jurisdiction} {x.credential_type} expires {x.expires_on} (board record), file by {x.due_date}."
            f" Rule: {x.source_url} (verified {x.last_verified})"
        )
    if a.needs_board_read:
        out += ["", f"Licenses with no expiry read from the board yet: {len(a.needs_board_read)}"]
        out += [
            f"  {x.clinician}: {x.jurisdiction} {x.credential_type}" for x in a.needs_board_read
        ]
    out += [
        "",
        f"Cost of the current gaps: service {_usd(a.gap_service_cents)}, state fees {_usd(a.gap_government_cents)} at cost"
        + (
            f" ({a.unpublished_fees} fee(s) not published by the board)"
            if a.unpublished_fees
            else ""
        )
        + ".",
        "Expiry dates are the ones the boards show; nothing here is calculated.",
    ]
    return "\n".join(out)


def quote(
    conn: sqlite3.Connection,
    org_id: str,
    as_of: str,
    *,
    rack_pppm_cents: int,
    tiers: Iterable[DiscountTier] = (),
) -> dict[str, object]:
    """Quote from obligations: one line per open filing plus the per-clinician subscription.

    The subscription discount applies after the rack rate and never takes the effective price
    below the $200 PPPM floor (pricing.effective_unit_price_cents).
    """
    a = roster_audit(conn, org_id, as_of)
    pct = discount_percent_for(a.clinicians, list(tiers))
    pppm = effective_unit_price_cents(rack_pppm_cents, pct, is_pppm_floored=True)
    filings = a.missing_states + a.upcoming
    lines: list[dict[str, object]] = [
        {
            "description": f"{x.clinician}: {x.jurisdiction} {x.credential_type} ({x.trigger})",
            "service_cents": x.price_cents,
            "government_fee_cents": x.government_fee_cents,
            "government_fee_label": "pass-through at cost"
            if x.government_fee_cents is not None
            else "not published",
            "source_url": x.source_url,
        }
        for x in filings
    ]
    return {
        "org": a.org_name,
        "as_of": as_of,
        "clinicians": a.clinicians,
        "subscription": {
            "rack_pppm_cents": rack_pppm_cents,
            "discount_percent": str(pct),
            "effective_pppm_cents": pppm,
            "monthly_cents": pppm * a.clinicians,
        },
        "filings": lines,
        "filings_service_cents": sum(x.price_cents for x in filings),
        "government_fees_cents": sum(x.government_fee_cents or 0 for x in filings),
    }
