"""Split-clock states: CSR clocks that do not track the licence (WP0.6).

Connecticut and Delaware run the controlled-substance registration on a fixed
calendar of their own; the csr_anchor rows in 60_clock_anchors.sql say so. These
drive the whole engine (plan) with those anchors and assert the CSR due date,
including Connecticut's three distinct clocks. Rhode Island tracks the licence
(the engine default) and needs no anchor.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from clinician_standing import engine as eng

AS_OF = date(2026, 9, 18)
CLINICIAN = UUID("cccccccc-0000-4000-8000-000000000001")
PRACTICE = UUID("aaaaaaaa-0000-4000-8000-000000000001")

# The anchors exactly as 60_clock_anchors.sql seeds them.
CT_CSR_ANCHOR = {"basis": "fixed", "month_day": "02-28", "parity": "odd"}
DE_CSR_ANCHOR = {"basis": "fixed", "month_day": "06-30", "parity": "odd"}


def _rule(state, lt, key, *, num=None, flag=None, jsonv=None, version=1):
    return eng.Rule(state, lt, key, num, flag, None, version, value_json=jsonv)


def _roster(state, rules, *, expiry):
    aff = eng.Affiliation(clinician_id=CLINICIAN, practice_id=PRACTICE, is_billing=True, tier=None)
    lic = eng.License(
        clinician_id=CLINICIAN,
        state=state,
        license_type="MD",
        status="active",
        expiry_date=expiry,
        issue_date=date(2025, 1, 1),
    )
    return eng.Roster(
        as_of=AS_OF,
        affiliations=(aff,),
        licenses=(lic,),
        rule_sets={(state, "MD"): eng.RuleSet(state, "MD", rules)},
    )


def _due(specs, obligation_type):
    match = [s for s in specs if s.obligation_type == obligation_type]
    assert match, f"no {obligation_type} spec planned"
    return match[0].due_date


def test_connecticut_csr_renews_on_28_february_of_odd_years() -> None:
    rules = {
        "csr_required": _rule("CT", "MD", "csr_required", flag=True),
        "csr_anchor": _rule("CT", "MD", "csr_anchor", jsonv=CT_CSR_ANCHOR),
    }
    specs = eng.plan(_roster("CT", rules, expiry=date(2027, 6, 30)))
    assert _due(specs, "csr_renewal") == date(2027, 2, 28)


def test_delaware_csr_renews_on_30_june_of_odd_years() -> None:
    rules = {
        "csr_required": _rule("DE", "MD", "csr_required", flag=True),
        "csr_anchor": _rule("DE", "MD", "csr_anchor", jsonv=DE_CSR_ANCHOR),
    }
    specs = eng.plan(_roster("DE", rules, expiry=date(2027, 3, 31)))
    assert _due(specs, "csr_renewal") == date(2027, 6, 30)


def test_connecticut_three_clocks_are_distinct() -> None:
    # CT/MD: licence renews every 12 months, CE cycle is 24 months, CSR is on the
    # 28 Feb odd-year schedule -- three clocks, the CSR one distinct from the
    # licence date.
    rules = {
        "renewal_cycle_months": _rule("CT", "MD", "renewal_cycle_months", num=Decimal(12)),
        "ce_hours_total": _rule("CT", "MD", "ce_hours_total", num=Decimal(50)),
        "ce_cycle_months": _rule("CT", "MD", "ce_cycle_months", num=Decimal(24)),
        "csr_required": _rule("CT", "MD", "csr_required", flag=True),
        "csr_anchor": _rule("CT", "MD", "csr_anchor", jsonv=CT_CSR_ANCHOR),
    }
    specs = eng.plan(_roster("CT", rules, expiry=date(2027, 6, 30)))
    types = {s.obligation_type for s in specs}
    assert {"license_renewal", "ce_cycle", "csr_renewal"} <= types
    assert _due(specs, "license_renewal") == date(2027, 6, 30)  # the licence's own date
    assert _due(specs, "csr_renewal") == date(2027, 2, 28)  # the CSR's own schedule
    assert _due(specs, "csr_renewal") != _due(specs, "license_renewal")


def test_rhode_island_csr_tracks_the_licence_by_default() -> None:
    # No csr_anchor: RI's CSR renews with the licence, so with no registration
    # row the engine treats it as the act of establishing one (as_of + lead).
    rules = {"csr_required": _rule("RI", "MD", "csr_required", flag=True)}
    specs = eng.plan(_roster("RI", rules, expiry=date(2027, 6, 30)))
    assert _due(specs, "csr_renewal") == AS_OF + timedelta(days=30)
