"""Anchors: the clocks that do not run off the credential's own date.

Pure tests for the anchor primitives, and plan-level tests that drive a whole
:class:`~clinician_standing.engine.Roster` through :func:`~clinician_standing.engine.plan`
to prove the wiring -- Connecticut's fixed-date CSR clock and Delaware's
issue-offset CSR clock -- without a database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from conftest import require

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing import engine as eng
except ImportError:  # pragma: no cover
    eng = None  # type: ignore[assignment]

needs_engine = require("clinician_standing.engine", "plan")

AS_OF = date(2026, 9, 18)
CLINICIAN = UUID("cccccccc-0000-4000-8000-000000000001")
PRACTICE = UUID("aaaaaaaa-0000-4000-8000-000000000001")


# --------------------------------------------------------------------------- #
# parse_anchor
# --------------------------------------------------------------------------- #


@needs_engine
def test_parse_anchor_fixed_with_month_day_shorthand() -> None:
    rule = eng.parse_anchor({"basis": "fixed", "month_day": "02-28", "parity": "odd"})
    assert rule == eng.AnchorRule(basis="fixed", month=2, day=28, parity="odd")


@needs_engine
def test_parse_anchor_issue_offset() -> None:
    rule = eng.parse_anchor({"basis": "issue", "offset_months": 6})
    assert rule == eng.AnchorRule(basis="issue", offset_months=6)


@needs_engine
@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"basis": "nonsense"},
        {"basis": "fixed"},  # fixed needs month/day
        {"basis": "fixed", "month": 13, "day": 1},
        "not a mapping",
    ],
)
def test_parse_anchor_rejects_bad_input(value: object) -> None:
    assert eng.parse_anchor(value) is None


@needs_engine
def test_parse_anchor_unknown_parity_defaults_annual() -> None:
    rule = eng.parse_anchor({"basis": "fixed", "month": 1, "day": 1, "parity": "leap"})
    assert rule is not None and rule.parity == "annual"


# --------------------------------------------------------------------------- #
# next_fixed_occurrence
# --------------------------------------------------------------------------- #


@needs_engine
@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (date(2026, 9, 18), date(2027, 2, 28)),  # next odd-year 28 Feb
        (date(2027, 1, 1), date(2027, 2, 28)),  # same odd year, before the date
        (date(2027, 3, 1), date(2029, 2, 28)),  # past it: skip to the next odd year
        (date(2027, 2, 28), date(2027, 2, 28)),  # on the day: today counts
    ],
)
def test_next_fixed_occurrence_odd_february(as_of: date, expected: date) -> None:
    assert eng.next_fixed_occurrence(2, 28, "odd", as_of) == expected


@needs_engine
def test_next_fixed_occurrence_clamps_leap_day() -> None:
    # 29 Feb on an even (non-leap) year clamps to the 28th rather than raising.
    assert eng.next_fixed_occurrence(2, 29, "even", date(2026, 1, 1)) == date(2026, 2, 28)


# --------------------------------------------------------------------------- #
# resolve_anchor
# --------------------------------------------------------------------------- #


@needs_engine
def test_resolve_anchor_none_is_credential_passthrough() -> None:
    cred = date(2027, 5, 31)
    got = eng.resolve_anchor(
        None, credential_anchor=cred, issue_date=None, expiry_date=cred, as_of=AS_OF
    )
    assert got == cred


@needs_engine
def test_resolve_anchor_issue_offset() -> None:
    rule = eng.AnchorRule(basis="issue", offset_months=6)
    got = eng.resolve_anchor(
        rule,
        credential_anchor=None,
        issue_date=date(2025, 3, 15),
        expiry_date=None,
        as_of=AS_OF,
    )
    assert got == date(2025, 9, 15)


@needs_engine
def test_resolve_anchor_missing_basis_falls_back_to_credential() -> None:
    rule = eng.AnchorRule(basis="issue")
    cred = date(2027, 1, 1)
    got = eng.resolve_anchor(
        rule, credential_anchor=cred, issue_date=None, expiry_date=None, as_of=AS_OF
    )
    assert got == cred


# --------------------------------------------------------------------------- #
# Plan-level: the wiring, proven through plan()
# --------------------------------------------------------------------------- #


def _rule(state, lt, key, *, num=None, flag=None, jsonv=None, version=1):  # noqa: ANN001, ANN201
    return eng.Rule(state, lt, key, num, flag, None, version, value_json=jsonv)


def _roster(rules: dict[str, object], *, expiry: date | None, issue: date | None):  # noqa: ANN001
    state, lt = "CT", "RN"
    aff = eng.Affiliation(clinician_id=CLINICIAN, practice_id=PRACTICE, is_billing=True, tier=None)
    lic = eng.License(
        clinician_id=CLINICIAN,
        state=state,
        license_type=lt,
        status="active",
        expiry_date=expiry,
        issue_date=issue,
    )
    return eng.Roster(
        as_of=AS_OF,
        affiliations=(aff,),
        licenses=(lic,),
        rule_sets={(state, lt): eng.RuleSet(state, lt, rules)},
    )


def _due(specs, obligation_type):  # noqa: ANN001
    match = [s for s in specs if s.obligation_type == obligation_type]
    assert match, f"no {obligation_type} spec was planned"
    return match[0].due_date


@needs_engine
def test_ct_csr_uses_fixed_february_schedule() -> None:
    """CT CSR renews 28 Feb of odd years, not on the licence anniversary."""
    rules = {
        "csr_required": _rule("CT", "RN", "csr_required", flag=True),
        "csr_anchor": _rule(
            "CT",
            "RN",
            "csr_anchor",
            jsonv={"basis": "fixed", "month_day": "02-28", "parity": "odd"},
        ),
    }
    specs = eng.plan(_roster(rules, expiry=date(2027, 6, 30), issue=date(2023, 6, 30)))
    assert _due(specs, "csr_renewal") == date(2027, 2, 28)


@needs_engine
def test_de_style_csr_uses_issue_offset() -> None:
    """An issue-offset CSR clock is dated from the licence issue, then rolled."""
    rules = {
        "csr_required": _rule("CT", "RN", "csr_required", flag=True),
        "csr_anchor": _rule(
            "CT", "RN", "csr_anchor", jsonv={"basis": "issue", "offset_months": 6}
        ),
    }
    # issue 2025-03-15 + 6 months = 2025-09-15; one 12-month cycle rolls it to
    # 2026-09-15, three days before AS_OF, so it surfaces as just past due.
    specs = eng.plan(_roster(rules, expiry=None, issue=date(2025, 3, 15)))
    assert _due(specs, "csr_renewal") == date(2026, 9, 15)


@needs_engine
def test_no_anchor_leaves_csr_on_the_credential() -> None:
    """With no csr_anchor, CSR falls to the establish path (no registration)."""
    rules = {"csr_required": _rule("CT", "RN", "csr_required", flag=True)}
    specs = eng.plan(_roster(rules, expiry=date(2027, 6, 30), issue=date(2023, 6, 30)))
    # No registration row and no anchor: compute_due_date treats it as the act of
    # establishing one, due at as_of + establish_lead_days (30).
    assert _due(specs, "csr_renewal") == date(2026, 10, 18)


@needs_engine
def test_ce_anchor_overrides_license_expiry_when_no_ledger() -> None:
    """A ce_anchor dates the CE cycle end even when the licence expiry differs."""
    rules = {
        "ce_hours_total": _rule("CT", "RN", "ce_hours_total", num=Decimal(24)),
        "ce_anchor": _rule(
            "CT",
            "RN",
            "ce_anchor",
            jsonv={"basis": "fixed", "month_day": "12-31", "parity": "even"},
        ),
    }
    specs = eng.plan(_roster(rules, expiry=date(2027, 6, 30), issue=date(2023, 6, 30)))
    # ce_anchor fixed 31 Dec even year -> 2026-12-31, not the 2027-06-30 expiry.
    assert _due(specs, "ce_cycle") == date(2026, 12, 31)
