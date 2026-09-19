"""The classifier's decision core (PRD section 8), case by case.

These are pure: every PRD 8.1 condition and every PRD 8.3 reason code is driven
through :func:`~clinician_standing.classifier.classify` against a fully-specified
:class:`~clinician_standing.classifier.ObligationFacts`. The database half
(gathering the facts, writing the routing) is exercised by the database-marked
integration tests.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from clinician_standing import classifier as clf

OID = UUID("00000000-0000-4000-8000-000000000001")
EVID = UUID("eeeeeeee-0000-4000-8000-000000000001")


def facts(**over: object):
    """A fully-verified, routine, not-yet-actionable license_renewal.

    By default every PRD 8.1 condition holds and there is no work to do, so it
    auto-clears. Each test overrides exactly the field it is about.
    """
    base = {
        "obligation_id": OID,
        "obligation_type": "license_renewal",
        "severity": "routine",
        "actionable": False,
        "has_primary_evidence": True,
        "evidence_fresh": True,
        "strong_single_match": True,
        "has_conflict": False,
        "rule_current": True,
        "open_conflict": False,
        "exclusion_hit": False,
        "lapsed_while_billing": False,
        "terms_lapsed": False,
        "evidence_id": EVID,
    }
    base.update(over)
    return clf.ObligationFacts(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_all_conditions_hold_not_actionable_auto_clears() -> None:
    d = clf.classify(facts())
    assert d.outcome == clf.OUTCOME_AUTO
    assert d.reason_code is None


def test_clean_fresh_screen_auto_clears_even_when_actionable() -> None:
    d = clf.classify(facts(obligation_type="exclusion_screen", actionable=True))
    assert d.outcome == clf.OUTCOME_AUTO


def test_routine_renewal_in_window_goes_to_action_queue() -> None:
    d = clf.classify(facts(actionable=True))
    assert d.outcome == clf.OUTCOME_QUEUED


def test_routine_revalidation_in_window_needs_a_portal() -> None:
    d = clf.classify(facts(obligation_type="medicare_revalidation", actionable=True))
    assert d.outcome == clf.OUTCOME_EXCEPTION
    assert d.reason_code == clf.PORTAL_REQUIRED


# --------------------------------------------------------------------------- #
# Each reason code
# --------------------------------------------------------------------------- #


def test_terms_lapsed_beats_everything() -> None:
    d = clf.classify(facts(terms_lapsed=True, exclusion_hit=True))
    assert d.reason_code == clf.TERMS_LAPSED


def test_exclusion_hit_is_high_consequence() -> None:
    d = clf.classify(facts(obligation_type="exclusion_screen", exclusion_hit=True))
    assert d.reason_code == clf.HIGH_CONSEQUENCE


def test_lapse_while_billing_is_high_consequence() -> None:
    d = clf.classify(facts(lapsed_while_billing=True))
    assert d.reason_code == clf.HIGH_CONSEQUENCE


def test_high_consequence_beats_stale_and_conflict() -> None:
    # An exclusion hit must surface even if the assertion is also stale.
    d = clf.classify(
        facts(obligation_type="exclusion_screen", exclusion_hit=True, evidence_fresh=False)
    )
    assert d.reason_code == clf.HIGH_CONSEQUENCE


def test_superseded_rule_is_skipped() -> None:
    d = clf.classify(facts(rule_current=False))
    assert d.outcome == clf.OUTCOME_SKIP


def test_open_conflict_is_rule_uncertain() -> None:
    d = clf.classify(facts(open_conflict=True))
    assert d.reason_code == clf.RULE_UNCERTAIN


def test_no_evidence_renewal_goes_to_action_queue() -> None:
    d = clf.classify(facts(has_primary_evidence=False))
    assert d.outcome == clf.OUTCOME_QUEUED


def test_no_evidence_ce_needs_a_document() -> None:
    d = clf.classify(facts(obligation_type="ce_cycle", has_primary_evidence=False))
    assert d.reason_code == clf.DOCUMENT_REQUIRED


def test_no_evidence_revalidation_needs_a_portal() -> None:
    d = clf.classify(facts(obligation_type="payer_revalidation", has_primary_evidence=False))
    assert d.reason_code == clf.PORTAL_REQUIRED


def test_stale_evidence_is_source_stale() -> None:
    d = clf.classify(facts(evidence_fresh=False))
    assert d.reason_code == clf.SOURCE_STALE


def test_weak_match_is_identity_ambiguous() -> None:
    d = clf.classify(facts(strong_single_match=False))
    assert d.reason_code == clf.IDENTITY_AMBIGUOUS


def test_disagreeing_sources_is_source_conflict() -> None:
    d = clf.classify(facts(has_conflict=True))
    assert d.reason_code == clf.SOURCE_CONFLICT


def test_elevated_routine_work_goes_to_action_queue() -> None:
    d = clf.classify(facts(severity="elevated"))
    assert d.outcome == clf.OUTCOME_QUEUED


# --------------------------------------------------------------------------- #
# generating_field + result instrumentation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("obligation_type", "field"),
    [
        ("license_renewal", "renewal_cycle_months"),
        ("csr_renewal", "csr_required"),
        ("ce_cycle", "ce_hours_total"),
        ("exclusion_screen", "exclusion_screen_cadence_months"),
    ],
)
def test_generating_field(obligation_type: str, field: str) -> None:
    assert clf.generating_field(obligation_type) == field


def test_result_auto_clear_rate_excludes_skips() -> None:
    result = clf.ClassifierResult(as_of=date(2026, 9, 18), dry_run=True)
    result.record(clf.Decision(clf.OUTCOME_AUTO))
    result.record(clf.Decision(clf.OUTCOME_AUTO))
    result.record(clf.Decision(clf.OUTCOME_QUEUED))
    result.record(clf.Decision(clf.OUTCOME_EXCEPTION, clf.SOURCE_STALE))
    result.record(clf.Decision(clf.OUTCOME_SKIP))  # excluded from the denominator
    assert result.decided == 4
    assert result.auto_clear_rate == 0.5
    assert result.by_reason == {clf.SOURCE_STALE: 1}


def test_result_auto_clear_rate_none_when_empty() -> None:
    result = clf.ClassifierResult(as_of=date(2026, 9, 18), dry_run=True)
    assert result.auto_clear_rate is None
