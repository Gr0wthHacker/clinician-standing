"""The obligations engine (PRD section 7, build phase 4).

Runs nightly and on any roster or rule change::

    for each active affiliation (clinician x practice):
      for each state the clinician holds a license in:
        rules = requirements.current(state, clinician.license_type)
        for each rule that generates a dated duty:
          due = compute_due_date(rule, existing credential row)
          upsert obligation(clinician, practice, type, state, due, rule_version)
      emit exclusion_screen obligation (monthly cadence, all clinicians)
      emit directory_attestation obligation (per payer cadence)

The module is deliberately split in two halves.

*Planning* is pure Python: :func:`plan` turns an in-memory :class:`Roster`
snapshot into a list of :class:`ObligationSpec`. It touches no database, so
due-date arithmetic, severity assignment and priority ordering are testable
without Postgres.

*Persistence* is one statement, :data:`UPSERT_SQL`, whose conflict target is
``ux_obligations_open_duty`` from ``0005_obligations.sql``. That index covers
the OPEN obligations for ``(clinician, practice, type, state, payer)`` and
deliberately excludes ``due_date``, so a rule change moves the date on the
existing row instead of forking a second duty. The inference clause below
reproduces the index expressions *and* its predicate exactly; anything less and
Postgres either refuses to infer an arbiter or silently picks another index,
which duplicates every obligation on every run.

Scale is small by design (PRD 12: 465 clinicians, ~5,000 open obligations), so
the whole roster is read into memory in a handful of queries rather than
walked with a cursor.
"""

from __future__ import annotations

import calendar
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from .config import Settings
from .db import connect, fetch_all, transaction

__all__ = [
    "CE_CLOSING_DAYS",
    "CLOSEABLE_ON_ROSTER_SHRINK",
    "DEFAULTS",
    "DUTY_FIELD_KEYS",
    "ELEVATED_WINDOW_DAYS",
    "OPEN_STATUSES",
    "PRIORITY_ORDER_SQL",
    "SEVERITY_RANK",
    "TIER_RANK",
    "UPSERT_SQL",
    "AnchorRule",
    "EngineResult",
    "ObligationSpec",
    "Roster",
    "RuleSet",
    "add_months",
    "compute_due_date",
    "load_roster",
    "month_end",
    "next_fixed_occurrence",
    "obligations_to_close",
    "parse_anchor",
    "plan",
    "priority_key",
    "resolve_anchor",
    "run",
    "run_engine",
    "severity_for",
    "sort_by_priority",
]

LOGGER = logging.getLogger(__name__)

#: Obligation statuses that count as OPEN. This is the predicate of
#: ``ux_obligations_open_duty`` and must stay identical to it.
OPEN_STATUSES: tuple[str, ...] = ("pending", "queued", "in_progress", "exception")

#: PRD 7: "elevated: due inside 30 days".
ELEVATED_WINDOW_DAYS = 30

#: A CE cycle is "closing" once its end is this near. A topic shortfall before
#: that is still recoverable inside the cycle and stays routine (PRD 7).
CE_CLOSING_DAYS = 120

#: Severity ordering for the queue (PRD 7).
SEVERITY_RANK: Mapping[str, int] = {"critical": 0, "elevated": 1, "routine": 2}

#: Account tier ordering for the queue (PRD 7, "then account tier"). Richer
#: tiers carry more service and break the tie first; an unset tier sorts last.
TIER_RANK: Mapping[str, int] = {"complete": 0, "standard": 1, "essential": 2}

#: Licence statuses that mean the clinician may not practise on that licence.
LAPSED_LICENSE_STATUSES: frozenset[str] = frozenset({"expired", "lapsed", "suspended", "revoked"})

#: Enrolment statuses that are themselves the finding (PRD 7).
TERMINATED_ENROLLMENT_STATUSES: frozenset[str] = frozenset({"terminated"})
REJECTED_ENROLLMENT_STATUSES: frozenset[str] = frozenset({"rejected"})

# ---------------------------------------------------------------------------
# The rules plane contract.
#
# PRD 5.3 names 7 of the 38 `requirements.field_key` values and does not publish
# the rest, and 0004_rules.sql declines to enumerate them for that reason. These
# are the keys the engine reads, with the fallback it uses when the rules plane
# has not loaded one for a (state, license_type). A default is a documented
# statutory norm, never a guess dressed up as a rule: an obligation generated
# from a default carries `rule_version = NULL`, so "this duty has no citation"
# is visible in the data rather than implied.
# ---------------------------------------------------------------------------
DEFAULTS: Mapping[str, int] = {
    # license_renewal
    "renewal_cycle_months": 24,
    "renewal_window_days": 90,
    # csr_renewal (state controlled-substance registration)
    "csr_cycle_months": 12,
    "csr_window_days": 60,
    # dea_renewal (federal, three-year term)
    "dea_cycle_months": 36,
    "dea_window_days": 60,
    # ce_cycle. ce_cycle_months defaults to the renewal cycle, because a CE
    # cycle that is not the renewal cycle is the exception, not the rule.
    "ce_cycle_months": 24,
    "ce_window_days": 365,
    # medicare_revalidation / payer_revalidation (CMS: five years, window opens
    # six months ahead)
    "revalidation_cycle_months": 60,
    "revalidation_window_days": 180,
    # privilege_reappointment
    "privilege_cycle_months": 24,
    "privilege_window_days": 120,
    # exclusion_screen: PRD 7 fixes the cadence at monthly.
    "exclusion_screen_cadence_months": 1,
    # directory_attestation: 90 days is the No Surprises Act directory cadence.
    "directory_attestation_cadence_months": 3,
    "directory_attestation_window_days": 30,
    # How long a clinician gets to establish a credential that does not exist
    # yet. The obligation is the act of establishing one.
    "establish_lead_days": 30,
}

#: Which field_key generates which obligation type. The FIRST key in each tuple
#: is the generating rule: its ``requirements.version`` becomes the obligation's
#: ``rule_version``. Later keys tune the same duty and raise the recorded
#: version if they are newer, so bumping either the cycle or its window is a
#: traceable change to the duty.
DUTY_FIELD_KEYS: Mapping[str, tuple[str, ...]] = {
    "license_renewal": ("renewal_cycle_months", "renewal_window_days", "renewal_anchor"),
    "csr_renewal": ("csr_required", "csr_cycle_months", "csr_window_days", "csr_anchor"),
    "dea_renewal": ("dea_required", "dea_cycle_months", "dea_window_days"),
    "ce_cycle": ("ce_hours_total", "ce_cycle_months", "ce_window_days", "ce_anchor"),
    "medicare_revalidation": ("revalidation_cycle_months", "revalidation_window_days"),
    "payer_revalidation": ("revalidation_cycle_months", "revalidation_window_days"),
    "privilege_reappointment": ("privilege_cycle_months", "privilege_window_days"),
    "exclusion_screen": ("exclusion_screen_cadence_months",),
    "directory_attestation": (
        "directory_attestation_cadence_months",
        "directory_attestation_window_days",
    ),
}

#: Payers whose revalidation is Medicare's, and therefore whose duty is the
#: ``medicare_revalidation`` type rather than ``payer_revalidation``.
MEDICARE_PAYERS: frozenset[str] = frozenset({"medicare"})


# ===========================================================================
# Date arithmetic
# ===========================================================================
def month_end(value: date) -> date:
    """Return the last calendar day of ``value``'s month."""
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def add_months(value: date, months: int) -> date:
    """Add ``months`` calendar months, clamping to the end of the target month.

    ``add_months(date(2026, 1, 31), 1)`` is 2026-02-28, not an error and not
    2026-03-03. Renewal cycles are expressed in months by every board that
    publishes one, so month arithmetic is the primitive, not 30-day steps.

    Args:
        value: Anchor date.
        months: Months to add; may be negative.

    Returns:
        The shifted date.
    """
    total = value.month - 1 + months
    year = value.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


# ===========================================================================
# Anchors -- where a clock starts, when it is not the credential's own date.
#
# By default the engine anchors a duty to the date the credential carries: a
# licence expiry, a CSR expiry, a CE cycle end. That is right for most states,
# and wrong for the ones whose clock runs on a schedule of its own:
#
#   * Connecticut's controlled-substance registration renews on 28 February of
#     odd years, not on the licence's anniversary. A ``fixed`` anchor.
#   * Delaware and Rhode Island run the CSR clock offset from the licence issue.
#     An ``issue`` anchor with ``offset_months``.
#   * A dozen states run the CE cycle off the renewal cycle; anchoring CE to the
#     licence expiry there is wrong even when the cycle LENGTH is right.
#
# An anchor is stored as a ``value_json`` requirement under a ``*_anchor``
# field_key (``renewal_anchor``, ``csr_anchor``, ``ce_anchor``), so it carries a
# citation and a version like every other rule and needs no new table. It is
# INERT until authored: with no anchor rule loaded, resolve_anchor returns the
# credential's own date and the calendar is exactly what it was.
# ===========================================================================

#: Where an anchor's clock starts.
VALID_ANCHOR_BASES: frozenset[str] = frozenset({"credential", "issue", "license_expiry", "fixed"})

#: Which years a ``fixed`` anchor lands on.
VALID_ANCHOR_PARITY: frozenset[str] = frozenset({"annual", "odd", "even"})


@dataclass(frozen=True)
class AnchorRule:
    """How to find the date a clock is anchored to.

    Attributes:
        basis: ``credential`` (the credential's own date, the default behaviour),
            ``issue`` (the licence issue date), ``license_expiry`` (the licence
            expiry) or ``fixed`` (a recurring calendar date).
        offset_months: Whole months added to the basis date. Delaware and Rhode
            Island CSR use this against ``issue``.
        month: For ``fixed``, the anchor month (1-12).
        day: For ``fixed``, the anchor day of month.
        parity: For ``fixed``, which years it lands on -- ``annual`` every year,
            ``odd``/``even`` every other year. Connecticut CSR is 28 Feb, odd.
    """

    basis: str
    offset_months: int = 0
    month: int | None = None
    day: int | None = None
    parity: str = "annual"


def _valid_month_day(month: Any, day: Any) -> bool:
    """True when ``month`` and ``day`` name a plausible calendar day."""
    try:
        return 1 <= int(month) <= 12 and 1 <= int(day) <= 31
    except (TypeError, ValueError):
        return False


def parse_anchor(value: Any) -> AnchorRule | None:
    """Parse a ``*_anchor`` requirement's ``value_json`` into an :class:`AnchorRule`.

    Lenient by design: a malformed anchor returns None and is logged rather than
    raising, so one bad rule row falls back to the credential's date instead of
    taking the whole nightly run down. ``month_day`` (``"02-28"``) is accepted as
    a shorthand for ``month`` and ``day``.

    Returns:
        An :class:`AnchorRule`, or None when the value is absent or unusable.
    """
    if not isinstance(value, Mapping):
        return None
    basis = str(value.get("basis", "")).strip().lower()
    if basis not in VALID_ANCHOR_BASES:
        LOGGER.warning("ignoring anchor with unknown basis %r", value.get("basis"))
        return None
    parity = str(value.get("parity", "annual")).strip().lower()
    if parity not in VALID_ANCHOR_PARITY:
        parity = "annual"
    month, day = value.get("month"), value.get("day")
    if (month is None or day is None) and value.get("month_day"):
        try:
            month_str, day_str = str(value["month_day"]).split("-")[:2]
            month, day = int(month_str), int(day_str)
        except (TypeError, ValueError):
            month, day = None, None
    try:
        offset = int(value.get("offset_months", 0) or 0)
    except (TypeError, ValueError):
        offset = 0
    if basis == "fixed" and not _valid_month_day(month, day):
        LOGGER.warning("ignoring fixed anchor without a valid month/day: %r", value)
        return None
    return AnchorRule(
        basis=basis,
        offset_months=offset,
        month=int(month) if month is not None else None,
        day=int(day) if day is not None else None,
        parity=parity,
    )


def next_fixed_occurrence(month: int, day: int, parity: str, as_of: date) -> date:
    """Return the next occurrence of ``month``/``day`` on or after ``as_of``.

    ``parity`` restricts the year: ``odd``/``even`` land only on odd/even years,
    which is how a biennial "28 Feb of odd years" schedule is expressed. The day
    is clamped to the month's length so 29 Feb never raises.

    Args:
        month: Anchor month (1-12).
        day: Anchor day of month.
        parity: ``annual`` | ``odd`` | ``even``.
        as_of: The run date.

    Returns:
        The next scheduled date, on or after ``as_of``.
    """
    year = as_of.year
    for _ in range(16):  # bounded: at most a few years for any parity
        if (parity == "odd" and year % 2 == 0) or (parity == "even" and year % 2 == 1):
            year += 1
            continue
        candidate = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if candidate >= as_of:
            return candidate
        year += 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def resolve_anchor(
    rule: AnchorRule | None,
    *,
    credential_anchor: date | None,
    issue_date: date | None,
    expiry_date: date | None,
    as_of: date,
) -> date | None:
    """Resolve the date a clock is anchored to.

    With no rule, or a ``credential`` basis, the credential's own date is used --
    the engine's default behaviour, unchanged. Otherwise the basis picks the
    licence issue date, the licence expiry, or a fixed calendar date, and
    ``offset_months`` shifts it. A basis whose source date is missing falls back
    to the credential date rather than inventing one.

    Args:
        rule: The anchor rule, or None.
        credential_anchor: The date the credential carries, or None.
        issue_date: The licence issue date, for the ``issue`` basis.
        expiry_date: The licence expiry, for the ``license_expiry`` basis.
        as_of: The run date, for the ``fixed`` basis.

    Returns:
        The resolved anchor date, or None when nothing supplies one.
    """
    if rule is None or rule.basis == "credential":
        return credential_anchor
    if rule.basis == "issue":
        base = issue_date
    elif rule.basis == "license_expiry":
        base = expiry_date
    elif rule.basis == "fixed" and rule.month is not None and rule.day is not None:
        base = next_fixed_occurrence(rule.month, rule.day, rule.parity, as_of)
    else:  # pragma: no cover - parse_anchor rejects any other basis
        return credential_anchor
    if base is None:
        return credential_anchor
    return add_months(base, rule.offset_months) if rule.offset_months else base


# ===========================================================================
# Rules plane
# ===========================================================================
@dataclass(frozen=True)
class Rule:
    """One current ``requirements`` row."""

    state: str
    license_type: str
    field_key: str
    value_num: Decimal | None
    value_bool: bool | None
    value_text: str | None
    version: int
    # Last field, defaulted: the existing seven-positional Rule(...) call sites
    # (and the tests) predate value_json and must keep working unchanged.
    value_json: Any = None


@dataclass(frozen=True)
class RuleSet:
    """The current requirements for one ``(state, license_type)`` pair."""

    state: str
    license_type: str
    rules: Mapping[str, Rule] = field(default_factory=dict)

    def months(self, key: str) -> int:
        """Return an integer rule value, falling back to :data:`DEFAULTS`."""
        rule = self.rules.get(key)
        if rule is not None and rule.value_num is not None:
            return int(rule.value_num)
        return DEFAULTS[key]

    def number(self, key: str) -> Decimal | None:
        """Return a numeric rule value, or None when the rule is not loaded."""
        rule = self.rules.get(key)
        return rule.value_num if rule is not None else None

    def flag(self, key: str, default: bool = False) -> bool:
        """Return a boolean rule value, or ``default`` when not loaded."""
        rule = self.rules.get(key)
        if rule is not None and rule.value_bool is not None:
            return rule.value_bool
        return default

    def has(self, key: str) -> bool:
        """True when the rules plane has loaded ``key`` for this pair."""
        return key in self.rules

    def anchor(self, key: str) -> AnchorRule | None:
        """Return the parsed anchor for ``key``, or None when not loaded.

        ``key`` is a ``*_anchor`` field_key (``renewal_anchor``, ``csr_anchor``,
        ``ce_anchor``). The anchor is stored in the rule's ``value_json``.
        """
        rule = self.rules.get(key)
        if rule is None or rule.value_json is None:
            return None
        return parse_anchor(rule.value_json)

    def version_for(self, obligation_type: str) -> int | None:
        """The ``requirements.version`` to stamp on an obligation of this type.

        Returns the highest version among the loaded keys that contribute to
        the duty, or None when none of them is loaded and the duty therefore
        rests on a :data:`DEFAULTS` value rather than on a cited rule.
        """
        versions = [
            self.rules[key].version
            for key in DUTY_FIELD_KEYS.get(obligation_type, ())
            if key in self.rules
        ]
        return max(versions) if versions else None

    def topic_requirements(self) -> dict[str, Decimal]:
        """CE topic mandates, keyed by ``ce_records.topic``.

        ``ce_topic_opioid_hours`` (PRD 5.3) becomes ``{"opioid": 3}``.
        """
        out: dict[str, Decimal] = {}
        for key, rule in self.rules.items():
            if (
                key.startswith("ce_topic_")
                and key.endswith("_hours")
                and rule.value_num is not None
            ):
                out[key[len("ce_topic_") : -len("_hours")]] = rule.value_num
        return out


# ===========================================================================
# Roster snapshot
# ===========================================================================
@dataclass(frozen=True)
class Affiliation:
    """An active clinician-practice pair, with the context severity needs."""

    clinician_id: UUID
    practice_id: UUID
    is_billing: bool
    tier: str | None


@dataclass(frozen=True)
class License:
    """A ``licenses`` row."""

    clinician_id: UUID
    state: str
    license_type: str
    status: str
    expiry_date: date | None
    issue_date: date | None

    def is_lapsed(self, as_of: date) -> bool:
        """True when this licence does not currently permit practice.

        PRD 7 says "license expired or suspended". A row still marked ``active``
        whose ``expiry_date`` has passed *is* expired -- the board moved on and
        our copy did not -- so the date is checked as well as the status.
        """
        if self.status in LAPSED_LICENSE_STATUSES:
            return True
        return self.expiry_date is not None and self.expiry_date < as_of


@dataclass(frozen=True)
class Registration:
    """A ``registrations`` row (DEA or state CSR)."""

    clinician_id: UUID
    kind: str
    state: str | None
    status: str | None
    expiry_date: date | None


@dataclass(frozen=True)
class Enrollment:
    """An ``enrollments`` row."""

    clinician_id: UUID
    practice_id: UUID | None
    payer: str
    status: str
    effective_date: date | None
    revalidation_due: date | None
    verified_at: datetime | None


@dataclass(frozen=True)
class Privilege:
    """A ``privileges`` row."""

    clinician_id: UUID
    facility_name: str | None
    reappointment_due: date | None
    granted_date: date | None


@dataclass(frozen=True)
class CeRecord:
    """A ``ce_records`` row."""

    clinician_id: UUID
    state: str | None
    cycle_start: date | None
    cycle_end: date | None
    topic: str | None
    hours: Decimal | None


@dataclass(frozen=True)
class Sanction:
    """A ``sanctions`` row. An unreinstated one is an exclusion hit."""

    clinician_id: UUID
    source: str
    action_date: date | None
    reinstated_date: date | None

    def is_active(self, as_of: date) -> bool:
        """True when the exclusion is still in force on ``as_of``."""
        return self.reinstated_date is None or self.reinstated_date > as_of


@dataclass(frozen=True)
class Roster:
    """Everything the engine needs, read once per run."""

    as_of: date
    affiliations: Sequence[Affiliation] = ()
    licenses: Sequence[License] = ()
    registrations: Sequence[Registration] = ()
    enrollments: Sequence[Enrollment] = ()
    privileges: Sequence[Privilege] = ()
    ce_records: Sequence[CeRecord] = ()
    sanctions: Sequence[Sanction] = ()
    rule_sets: Mapping[tuple[str, str], RuleSet] = field(default_factory=dict)

    def rules_for(self, state: str, license_type: str) -> RuleSet:
        """Current requirements for a pair, empty when the state is not loaded."""
        found = self.rule_sets.get((state, license_type))
        return found if found is not None else RuleSet(state, license_type, {})


# ===========================================================================
# Obligation specs
# ===========================================================================
@dataclass(frozen=True)
class ObligationSpec:
    """One dated duty, before it is written.

    ``is_billing``, ``tier`` and ``reason`` are not columns on ``obligations``;
    they are carried here because priority ordering and the dry-run report need
    them and re-reading the roster to get them back would be silly.
    """

    clinician_id: UUID
    practice_id: UUID
    obligation_type: str
    state: str | None
    payer: str | None
    due_date: date
    window_opens: date | None
    severity: str
    rule_version: int | None
    is_billing: bool = True
    tier: str | None = None
    reason: str = ""

    @property
    def key(self) -> tuple[UUID, UUID, str, str, str]:
        """The identity of the duty: the columns of ``ux_obligations_open_duty``."""
        return (
            self.clinician_id,
            self.practice_id,
            self.obligation_type,
            self.state or "",
            self.payer or "",
        )

    def parameters(self, generated_at: datetime) -> dict[str, Any]:
        """Bind parameters for :data:`UPSERT_SQL`."""
        return {
            "clinician_id": self.clinician_id,
            "practice_id": self.practice_id,
            "obligation_type": self.obligation_type,
            "state": self.state,
            "payer": self.payer,
            "due_date": self.due_date,
            "window_opens": self.window_opens,
            "severity": self.severity,
            "rule_version": self.rule_version,
            "generated_at": generated_at,
        }


def _clamp_window(window_opens: date, due_date: date) -> date:
    """Keep ``window_opens <= due_date`` (``obligations_window_chk``)."""
    return min(window_opens, due_date)


def compute_due_date(
    rules: RuleSet,
    obligation_type: str,
    anchor: date | None,
    as_of: date,
    *,
    cycle_key: str | None = None,
    window_key: str | None = None,
) -> tuple[date, date]:
    """Compute ``(due_date, window_opens)`` for one duty.

    Two cases, and the difference matters:

    * ``anchor`` is a date carried by an existing credential row -- a licence
      ``expiry_date``, an enrolment ``revalidation_due``, a CE ``cycle_end``.
      The duty is to renew it, so the due date *is* that date, rolled forward
      by whole cycles if it is already behind us and the credential has since
      been renewed silently.
    * ``anchor`` is None because no credential row exists yet. Then the
      obligation is the act of establishing one, which is due almost at once:
      ``as_of + establish_lead_days``, actionable immediately.

    Args:
        rules: Current requirements for the state and licence type.
        obligation_type: The duty being dated, used to pick default keys.
        anchor: The credential row's own date, or None.
        as_of: The run date.
        cycle_key: ``requirements.field_key`` holding the cycle length in
            months. Defaults to the first numeric key for the type.
        window_key: ``requirements.field_key`` holding the lead time in days.

    Returns:
        ``(due_date, window_opens)``.
    """
    cycle_key = cycle_key or _default_cycle_key(obligation_type)
    window_key = window_key or _default_window_key(obligation_type)
    window_days = rules.months(window_key) if window_key else 0

    if anchor is None:
        due = as_of + _days(rules.months("establish_lead_days"))
        return due, as_of

    due = anchor
    if cycle_key:
        cycle_months = rules.months(cycle_key)
        # A due date in the past is a real finding, not a bug, and must stay in
        # the past so severity can see it. It is only rolled forward when the
        # anchor is more than a full cycle stale, which means the credential was
        # renewed without us observing it.
        if cycle_months > 0:
            while due < as_of and add_months(due, cycle_months) < as_of:
                due = add_months(due, cycle_months)
    return due, _clamp_window(due - _days(window_days), due)


def _days(count: int) -> timedelta:
    """``timedelta(days=count)``, spelled once."""
    return timedelta(days=count)


def _default_cycle_key(obligation_type: str) -> str | None:
    keys = DUTY_FIELD_KEYS.get(obligation_type, ())
    for key in keys:
        if key.endswith("_months"):
            return key
    return None


def _default_window_key(obligation_type: str) -> str | None:
    keys = DUTY_FIELD_KEYS.get(obligation_type, ())
    for key in keys:
        if key.endswith("_days"):
            return key
    return None


# ===========================================================================
# Severity (PRD 7)
# ===========================================================================
def severity_for(
    obligation_type: str,
    due_date: date,
    as_of: date,
    *,
    is_billing: bool,
    lapsed_license: bool = False,
    exclusion_hit: bool = False,
    enrollment_status: str | None = None,
    ce_topic_shortfall: bool = False,
    cadence_months: int | None = None,
) -> tuple[str, str]:
    """Assign severity per PRD 7 and return ``(severity, reason)``.

    ``critical``
        Exclusion hit; licence expired or suspended while ``is_billing``;
        enrolment terminated; revalidation past due.
    ``elevated``
        Due inside 30 days; a first-pass rejection needing rework; CE cycle
        closing with a topic shortfall.
    ``routine``
        Everything else.

    Args:
        obligation_type: The duty's type.
        due_date: Its due date.
        as_of: The run date.
        is_billing: ``affiliations.is_billing`` for this pair. A lapse only
            reaches critical when the clinician bills under the practice.
        lapsed_license: The licence behind this duty is expired or suspended.
        exclusion_hit: An unreinstated sanction exists for this clinician.
        enrollment_status: ``enrollments.status`` behind this duty, if any.
        ce_topic_shortfall: A CE topic mandate is unmet.
        cadence_months: How often this duty recurs, in months. A duty that comes
            round at least monthly -- i.e. at least as often as the 30-day
            escalation window -- is never escalated for proximity alone. See
            INTERPRETATION below.

    Returns:
        ``(severity, reason)`` where reason is a short human-readable cause.

    INTERPRETATION. "Due inside 30 days" read literally makes the monthly
    exclusion screen permanently elevated, because a monthly duty is never more
    than 31 days out. That is one obligation per clinician per month -- the
    largest single class in the table -- and only ``routine`` may auto-clear
    (0005_obligations.sql, PRD 8.1 condition 7), so the literal reading would
    push every exclusion screen into a human queue and put the auto-clear rate,
    "the single metric that determines whether this business works" (PRD 1.1),
    out of reach by construction. The rule is therefore read as proximity
    *relative to the cadence*: it escalates a duty that comes round less often
    than the window, which is every duty the clause was written about.
    """
    days_to_due = (due_date - as_of).days
    revalidation = obligation_type in ("medicare_revalidation", "payer_revalidation")
    # One month is the 30-day window, within the slop of a calendar month.
    recurs_within_window = cadence_months is not None and cadence_months <= 1

    if exclusion_hit:
        return "critical", "exclusion hit"
    if lapsed_license and is_billing:
        return "critical", "license expired or suspended while billing"
    if enrollment_status in TERMINATED_ENROLLMENT_STATUSES:
        return "critical", "enrollment terminated"
    if revalidation and days_to_due < 0:
        return "critical", "revalidation past due"

    if enrollment_status in REJECTED_ENROLLMENT_STATUSES:
        return "elevated", "first-pass rejection needing rework"
    if ce_topic_shortfall and days_to_due <= CE_CLOSING_DAYS:
        return "elevated", "CE cycle closing with a topic shortfall"
    if days_to_due <= ELEVATED_WINDOW_DAYS and not recurs_within_window:
        return "elevated", f"due in {days_to_due} days"
    return "routine", ""


# ===========================================================================
# Priority ordering (PRD 7)
# ===========================================================================
def priority_key(spec: ObligationSpec, as_of: date) -> tuple[int, int, int, int]:
    """Queue ordering key: severity, days-to-due, billing first, account tier."""
    return (
        SEVERITY_RANK.get(spec.severity, len(SEVERITY_RANK)),
        (spec.due_date - as_of).days,
        0 if spec.is_billing else 1,
        TIER_RANK.get(spec.tier or "", len(TIER_RANK)),
    )


def sort_by_priority(specs: Iterable[ObligationSpec], as_of: date) -> list[ObligationSpec]:
    """Return ``specs`` in queue order (PRD 7)."""
    return sorted(specs, key=lambda spec: priority_key(spec, as_of))


#: The same ordering, for a queue view or a PostgREST ``order=`` clause. Kept
#: beside :func:`priority_key` so the two cannot drift apart unnoticed.
PRIORITY_ORDER_SQL = """
order by case o.severity
             when 'critical' then 0
             when 'elevated' then 1
             when 'routine'  then 2
             else 3
         end,
         (o.due_date - current_date),
         case when a.is_billing then 0 else 1 end,
         case p.tier
             when 'complete'  then 0
             when 'standard'  then 1
             when 'essential' then 2
             else 3
         end
"""


# ===========================================================================
# Planning -- pure, no database
# ===========================================================================
def plan(roster: Roster) -> list[ObligationSpec]:
    """Turn a roster snapshot into the obligations it implies.

    This is the loop in PRD section 7, verbatim. It is deterministic and has no
    side effects, which is what makes the calendar testable.

    Args:
        roster: The snapshot read by :func:`load_roster`.

    Returns:
        One spec per duty, deduplicated on
        ``(clinician, practice, type, state, payer)`` -- the identity of
        ``ux_obligations_open_duty``. A later spec for a key wins, which can
        only happen when two credential rows imply the same duty; the one with
        the earlier due date is kept, because the earlier date is the binding
        one.
    """
    by_clinician_licenses: dict[UUID, list[License]] = {}
    for lic in roster.licenses:
        by_clinician_licenses.setdefault(lic.clinician_id, []).append(lic)

    specs: list[ObligationSpec] = []
    for aff in roster.affiliations:
        licenses = by_clinician_licenses.get(aff.clinician_id, [])
        states = sorted({lic.state for lic in licenses})

        for state in states:
            for lic in sorted(
                (li for li in licenses if li.state == state),
                key=lambda li: li.license_type,
            ):
                rules = roster.rules_for(state, lic.license_type)
                specs.extend(_state_duties(roster, aff, lic, rules))

        specs.extend(_federal_duties(roster, aff, states))
        specs.extend(_enrollment_duties(roster, aff))
        specs.extend(_privilege_duties(roster, aff))
        specs.append(_exclusion_screen(roster, aff, states))
        specs.extend(_directory_attestations(roster, aff, states))

    return _dedupe(specs)


def _dedupe(specs: Sequence[ObligationSpec]) -> list[ObligationSpec]:
    """Collapse specs sharing an open-duty key, keeping the earliest due date."""
    chosen: dict[tuple[UUID, UUID, str, str, str], ObligationSpec] = {}
    for spec in specs:
        current = chosen.get(spec.key)
        if current is None or spec.due_date < current.due_date:
            chosen[spec.key] = spec
    return list(chosen.values())


def _spec(
    aff: Affiliation,
    obligation_type: str,
    state: str | None,
    payer: str | None,
    due: date,
    window: date | None,
    severity: str,
    reason: str,
    rule_version: int | None,
) -> ObligationSpec:
    return ObligationSpec(
        clinician_id=aff.clinician_id,
        practice_id=aff.practice_id,
        obligation_type=obligation_type,
        state=state,
        payer=payer,
        due_date=due,
        window_opens=window,
        severity=severity,
        rule_version=rule_version,
        is_billing=aff.is_billing,
        tier=aff.tier,
        reason=reason,
    )


def _state_duties(
    roster: Roster, aff: Affiliation, lic: License, rules: RuleSet
) -> list[ObligationSpec]:
    """license_renewal, csr_renewal and ce_cycle for one licence."""
    as_of = roster.as_of
    out: list[ObligationSpec] = []
    lapsed = lic.is_lapsed(as_of)

    # --- license_renewal ---------------------------------------------------
    # The anchor is the board's own expiry date when we have one. When we only
    # have an issue date -- several boards publish the issue and leave the term
    # to the statute -- the anchor is the issue date plus the published renewal
    # cycle, so `renewal_cycle_months` is load-bearing and a new version of it
    # moves the duty. With neither, no credential row is really established and
    # compute_due_date treats the obligation as the act of establishing one.
    anchor = lic.expiry_date
    if anchor is None and lic.issue_date is not None:
        anchor = add_months(lic.issue_date, rules.months("renewal_cycle_months"))
    # An authored renewal_anchor overrides the credential date; with none loaded
    # this returns `anchor` unchanged (the default, correct in most states).
    anchor = resolve_anchor(
        rules.anchor("renewal_anchor"),
        credential_anchor=anchor,
        issue_date=lic.issue_date,
        expiry_date=lic.expiry_date,
        as_of=as_of,
    )
    due, window = compute_due_date(rules, "license_renewal", anchor, as_of)
    severity, reason = severity_for(
        "license_renewal",
        due,
        as_of,
        is_billing=aff.is_billing,
        lapsed_license=lapsed,
        exclusion_hit=False,
    )
    out.append(
        _spec(
            aff,
            "license_renewal",
            lic.state,
            None,
            due,
            window,
            severity,
            reason,
            rules.version_for("license_renewal"),
        )
    )

    # --- csr_renewal -------------------------------------------------------
    if rules.flag("csr_required"):
        csr = _find_registration(roster, aff.clinician_id, "state_csr", lic.state)
        # CT (28 Feb, odd years), DE and RI (licence issue + offset) run the CSR
        # clock off a schedule of their own, expressed as a csr_anchor. With no
        # anchor loaded this is just the registration's expiry, as before.
        anchor = resolve_anchor(
            rules.anchor("csr_anchor"),
            credential_anchor=csr.expiry_date if csr is not None else None,
            issue_date=lic.issue_date,
            expiry_date=lic.expiry_date,
            as_of=as_of,
        )
        due, window = compute_due_date(rules, "csr_renewal", anchor, as_of)
        severity, reason = severity_for(
            "csr_renewal",
            due,
            as_of,
            is_billing=aff.is_billing,
            lapsed_license=lapsed,
            exclusion_hit=False,
        )
        out.append(
            _spec(
                aff,
                "csr_renewal",
                lic.state,
                None,
                due,
                window,
                severity,
                reason,
                rules.version_for("csr_renewal"),
            )
        )

    # --- ce_cycle ----------------------------------------------------------
    if rules.has("ce_hours_total") or rules.topic_requirements():
        cycle_end, cycle_start = _ce_cycle_bounds(roster, aff.clinician_id, lic, rules)
        shortfall = _ce_shortfall(roster, aff.clinician_id, lic.state, cycle_end, rules)
        window = _clamp_window(cycle_start, cycle_end)
        severity, reason = severity_for(
            "ce_cycle",
            cycle_end,
            as_of,
            is_billing=aff.is_billing,
            lapsed_license=lapsed,
            ce_topic_shortfall=shortfall,
        )
        out.append(
            _spec(
                aff,
                "ce_cycle",
                lic.state,
                None,
                cycle_end,
                window,
                severity,
                reason,
                rules.version_for("ce_cycle"),
            )
        )

    # An exclusion hit is a finding about the clinician, not about the licence
    # renewal in front of you. It is raised once, on the exclusion_screen
    # obligation, rather than smeared across every duty the clinician has, so
    # the exception queue gets one HIGH_CONSEQUENCE item and not fifteen.
    return out


def _federal_duties(
    roster: Roster, aff: Affiliation, states: Sequence[str]
) -> list[ObligationSpec]:
    """dea_renewal. Federal, so ``state`` is null (0003: "null for DEA")."""
    dea = _find_registration(roster, aff.clinician_id, "dea", None)
    rules = _first_ruleset(roster, aff, states)
    required = rules.flag("dea_required") or dea is not None
    if not required:
        return []
    due, window = compute_due_date(
        rules, "dea_renewal", dea.expiry_date if dea else None, roster.as_of
    )
    severity, reason = severity_for("dea_renewal", due, roster.as_of, is_billing=aff.is_billing)
    return [
        _spec(
            aff,
            "dea_renewal",
            None,
            None,
            due,
            window,
            severity,
            reason,
            rules.version_for("dea_renewal"),
        )
    ]


def _enrollment_duties(roster: Roster, aff: Affiliation) -> list[ObligationSpec]:
    """medicare_revalidation and payer_revalidation, one per payer."""
    out: list[ObligationSpec] = []
    rules = RuleSet("", "", {})
    for enr in _enrollments_for(roster, aff):
        obligation_type = (
            "medicare_revalidation" if enr.payer in MEDICARE_PAYERS else "payer_revalidation"
        )
        anchor = enr.revalidation_due
        if anchor is None and enr.effective_date is not None:
            anchor = add_months(enr.effective_date, DEFAULTS["revalidation_cycle_months"])
        due, window = compute_due_date(rules, obligation_type, anchor, roster.as_of)
        severity, reason = severity_for(
            obligation_type,
            due,
            roster.as_of,
            is_billing=aff.is_billing,
            enrollment_status=enr.status,
        )
        out.append(
            _spec(
                aff,
                obligation_type,
                None,
                enr.payer,
                due,
                window,
                severity,
                reason,
                None,
            )
        )
    return out


def _privilege_duties(roster: Roster, aff: Affiliation) -> list[ObligationSpec]:
    """privilege_reappointment. One per clinician-practice, earliest due wins.

    ``privileges`` has no practice or facility key the obligation can carry --
    ``ux_obligations_open_duty`` keys on (clinician, practice, type, state,
    payer) and privileges are facility-scoped -- so multiple facilities collapse
    to the nearest reappointment. :func:`_dedupe` does the collapsing.
    """
    rules = RuleSet("", "", {})
    out: list[ObligationSpec] = []
    for priv in roster.privileges:
        if priv.clinician_id != aff.clinician_id or priv.reappointment_due is None:
            continue
        due, window = compute_due_date(
            rules, "privilege_reappointment", priv.reappointment_due, roster.as_of
        )
        severity, reason = severity_for(
            "privilege_reappointment", due, roster.as_of, is_billing=aff.is_billing
        )
        out.append(
            _spec(
                aff,
                "privilege_reappointment",
                None,
                None,
                due,
                window,
                severity,
                reason,
                None,
            )
        )
    return out


def _exclusion_screen(roster: Roster, aff: Affiliation, states: Sequence[str]) -> ObligationSpec:
    """The monthly exclusion screen, emitted for EVERY clinician (PRD 7).

    Anchored to the calendar month rather than to "30 days from the last run",
    so a run on the 3rd and a run on the 27th produce the same due date and the
    cadence cannot drift. A screen that has already found something is critical.
    """
    as_of = roster.as_of
    rules = _first_ruleset(roster, aff, states)
    cadence = rules.months("exclusion_screen_cadence_months")
    due = month_end(add_months(as_of, cadence - 1))
    window = as_of.replace(day=1)
    hit = _has_exclusion(roster, aff.clinician_id)
    severity, reason = severity_for(
        "exclusion_screen",
        due,
        as_of,
        is_billing=aff.is_billing,
        exclusion_hit=hit,
        cadence_months=cadence,
    )
    return _spec(
        aff,
        "exclusion_screen",
        None,
        None,
        due,
        _clamp_window(window, due),
        severity,
        reason,
        rules.version_for("exclusion_screen"),
    )


def _directory_attestations(
    roster: Roster, aff: Affiliation, states: Sequence[str]
) -> list[ObligationSpec]:
    """directory_attestation, one per payer, at that payer's cadence (PRD 7).

    The schema carries no per-payer cadence column, so the cadence comes from
    the rules plane when it is loaded and from
    ``directory_attestation_cadence_months`` otherwise -- 90 days, the No
    Surprises Act directory cadence. The anchor is the enrolment's
    ``verified_at``: the last time anyone confirmed what the directory says.
    """
    as_of = roster.as_of
    rules = _first_ruleset(roster, aff, states)
    cadence = rules.months("directory_attestation_cadence_months")
    window_days = rules.months("directory_attestation_window_days")
    out: list[ObligationSpec] = []
    for enr in _enrollments_for(roster, aff):
        last = enr.verified_at.date() if enr.verified_at is not None else None
        if last is None:
            due = as_of + _days(rules.months("establish_lead_days"))
            window = as_of
        else:
            due = add_months(last, cadence)
            while due < as_of:
                due = add_months(due, cadence)
            window = _clamp_window(due - _days(window_days), due)
        severity, reason = severity_for(
            "directory_attestation",
            due,
            as_of,
            is_billing=aff.is_billing,
            enrollment_status=enr.status,
        )
        out.append(
            _spec(
                aff,
                "directory_attestation",
                None,
                enr.payer,
                due,
                window,
                severity,
                reason,
                rules.version_for("directory_attestation"),
            )
        )
    return out


# --------------------------------------------------------------- lookups
def _first_ruleset(roster: Roster, aff: Affiliation, states: Sequence[str]) -> RuleSet:
    """A rule set to read non-state-scoped cadences from.

    Federal and payer duties are not state-scoped, but the rules plane is the
    only place a cadence can be overridden with a citation. The clinician's
    states are consulted in alphabetical order so the choice is deterministic,
    and the first loaded set wins.
    """
    for key in sorted(roster.rule_sets):
        if key[0] in states:
            return roster.rule_sets[key]
    return RuleSet("", "", {})


def _find_registration(
    roster: Roster, clinician_id: UUID, kind: str, state: str | None
) -> Registration | None:
    for reg in roster.registrations:
        if reg.clinician_id == clinician_id and reg.kind == kind and reg.state == state:
            return reg
    return None


def _enrollments_for(roster: Roster, aff: Affiliation) -> list[Enrollment]:
    """Enrolments for this pair, one per payer, deterministic order."""
    seen: dict[str, Enrollment] = {}
    for enr in roster.enrollments:
        if enr.clinician_id != aff.clinician_id:
            continue
        if enr.practice_id is not None and enr.practice_id != aff.practice_id:
            continue
        seen.setdefault(enr.payer, enr)
    return [seen[payer] for payer in sorted(seen)]


def _has_exclusion(roster: Roster, clinician_id: UUID) -> bool:
    return any(
        s.clinician_id == clinician_id and s.is_active(roster.as_of) for s in roster.sanctions
    )


def _ce_cycle_bounds(
    roster: Roster, clinician_id: UUID, lic: License, rules: RuleSet
) -> tuple[date, date]:
    """Return ``(cycle_end, cycle_start)`` for a CE cycle.

    Boundaries come from ``ce_records`` when the clinician has any for the
    state. Otherwise the cycle is assumed to close with the licence, which is
    how the great majority of boards write it, and its length comes from
    ``ce_cycle_months`` -- defaulting to ``renewal_cycle_months``, because a CE
    cycle that is not the renewal cycle is the exception, not the rule.
    """
    cycle_months = (
        rules.months("ce_cycle_months")
        if rules.has("ce_cycle_months")
        else rules.months("renewal_cycle_months")
    )
    ends = [
        rec.cycle_end
        for rec in roster.ce_records
        if rec.clinician_id == clinician_id and rec.state == lic.state and rec.cycle_end is not None
    ]
    if ends:
        cycle_end = max(e for e in ends if e is not None)
    else:
        # No CE ledger for this state: anchor the cycle end. A ce_anchor states
        # the CE clock outright; failing that a renewal_anchor carries it (CE
        # tracks renewal in most states); failing both it is the licence expiry,
        # exactly as before. Only when none of those yields a date does it fall
        # to as_of + the cycle length.
        ce_rule = rules.anchor("ce_anchor") or rules.anchor("renewal_anchor")
        anchored = resolve_anchor(
            ce_rule,
            credential_anchor=lic.expiry_date,
            issue_date=lic.issue_date,
            expiry_date=lic.expiry_date,
            as_of=roster.as_of,
        )
        cycle_end = anchored if anchored is not None else add_months(roster.as_of, cycle_months)

    starts = [
        rec.cycle_start
        for rec in roster.ce_records
        if rec.clinician_id == clinician_id
        and rec.state == lic.state
        and rec.cycle_start is not None
    ]
    cycle_start = min(starts) if starts else add_months(cycle_end, -cycle_months)
    return cycle_end, cycle_start


def _ce_shortfall(
    roster: Roster,
    clinician_id: UUID,
    state: str,
    cycle_end: date,
    rules: RuleSet,
) -> bool:
    """True when a CE topic mandate, or the total, is unmet for the cycle."""
    mandates = rules.topic_requirements()
    total_required = rules.number("ce_hours_total")
    logged: dict[str, Decimal] = {}
    total = Decimal(0)
    for rec in roster.ce_records:
        if rec.clinician_id != clinician_id or rec.state != state:
            continue
        if rec.cycle_end is not None and rec.cycle_end != cycle_end:
            continue
        hours = rec.hours or Decimal(0)
        total += hours
        if rec.topic:
            logged[rec.topic] = logged.get(rec.topic, Decimal(0)) + hours
    if total_required is not None and total < total_required:
        return True
    return any(logged.get(topic, Decimal(0)) < required for topic, required in mandates.items())


# ===========================================================================
# Persistence
# ===========================================================================
#
# CONFLICT TARGET. `ux_obligations_open_duty` (0005_obligations.sql) is a
# PARTIAL unique index over expressions. Postgres infers a partial index as the
# arbiter only when the inference clause repeats BOTH the indexed expressions,
# in order, AND a predicate that implies the index predicate. Naming the columns
# without `coalesce(...)`, or omitting the `where`, does not merely perform
# worse -- it raises "no unique or exclusion constraint matching the ON CONFLICT
# specification", or, worse, matches a different index and duplicates the row.
#
# due_date is NOT in the key on purpose: a rule change must move the date on the
# open row, not fork a second duty. status is not in SET either -- an obligation
# a delivery associate has already moved to in_progress stays in_progress when
# its date shifts.
#
# The `where` on DO UPDATE makes an unchanged duty a no-op: `generated_at` only
# advances when something actually moved, so "what did last night's run change"
# is answerable from the table.
UPSERT_SQL = """
insert into obligations (
    clinician_id, practice_id, obligation_type, state, payer,
    due_date, window_opens, severity, status, rule_version, generated_at)
values (
    %(clinician_id)s, %(practice_id)s, %(obligation_type)s, %(state)s, %(payer)s,
    %(due_date)s, %(window_opens)s, %(severity)s, 'pending', %(rule_version)s,
    %(generated_at)s)
on conflict (clinician_id, practice_id, obligation_type,
             coalesce(state, ''), coalesce(payer, ''))
where status in ('pending','queued','in_progress','exception')
  and deleted_at is null
do update set
    due_date     = excluded.due_date,
    window_opens = excluded.window_opens,
    severity     = excluded.severity,
    rule_version = excluded.rule_version,
    generated_at = excluded.generated_at
where obligations.due_date     is distinct from excluded.due_date
   or obligations.window_opens is distinct from excluded.window_opens
   or obligations.severity     is distinct from excluded.severity
   or obligations.rule_version is distinct from excluded.rule_version
returning id, (xmax = 0) as inserted
"""

_QUERY_AFFILIATIONS = """
select a.clinician_id, a.practice_id, coalesce(a.is_billing, true), p.tier
from affiliations a
join clinicians c on c.id = a.clinician_id and c.deleted_at is null
join practices  p on p.id = a.practice_id  and p.deleted_at is null
where a.deleted_at is null
  and (a.end_date is null or a.end_date > %(as_of)s)
  and (a.start_date is null or a.start_date <= %(as_of)s)
order by a.clinician_id, a.practice_id
"""

_QUERY_LICENSES = """
select clinician_id, state, license_type, status, expiry_date, issue_date
from licenses
where deleted_at is null
order by clinician_id, state, license_type
"""

_QUERY_REGISTRATIONS = """
select clinician_id, kind, state, status, expiry_date
from registrations
where deleted_at is null
order by clinician_id, kind, state
"""

# `status` is read from the base table on purpose, not from the
# `enrollments_current` view (0012_enrollment_status_view.sql). That migration's
# rule is "a fact derived from a date and today is computed when it is read":
# the base column holds the decision the SOURCE asserted -- approved, pending,
# rejected, terminated -- and the view folds in a `current_date` comparison on
# top. The engine wants exactly the source's decision, because it does the date
# comparison itself, against `as_of` rather than `current_date`. Reading the
# view would make a run's answers depend on the wall clock instead of on the
# date the run was asked about, and a calendar that cannot be recomputed for a
# past date cannot be audited.
_QUERY_ENROLLMENTS = """
select clinician_id, practice_id, payer, status, effective_date,
       revalidation_due, verified_at
from enrollments
where deleted_at is null
order by clinician_id, practice_id, payer
"""

_QUERY_PRIVILEGES = """
select clinician_id, facility_name, reappointment_due, granted_date
from privileges
where deleted_at is null
order by clinician_id, reappointment_due
"""

_QUERY_CE = """
select clinician_id, state, cycle_start, cycle_end, topic, hours
from ce_records
where deleted_at is null
order by clinician_id, state, cycle_end
"""

_QUERY_SANCTIONS = """
select clinician_id, source, action_date, reinstated_date
from sanctions
where deleted_at is null
order by clinician_id, action_date
"""

# is_current is the contract: 0004 enforces one current row per
# (state, license_type, field_key) with ux_requirements_current, which is what
# makes "the rule version used is is_current" decidable (PRD 8.1 condition 5).
_QUERY_REQUIREMENTS = """
select state, license_type, field_key, value_num, value_bool, value_text, value_json, version
from requirements
where is_current and deleted_at is null
order by state, license_type, field_key
"""

_QUERY_OPEN_OBLIGATIONS = """
select clinician_id, practice_id, obligation_type,
       coalesce(state, ''), coalesce(payer, ''),
       due_date, window_opens, severity, rule_version
from obligations
where status in ('pending','queued','in_progress','exception')
  and deleted_at is null
"""

_QUERY_OPEN_OBLIGATION_IDS = """
select id, clinician_id, practice_id, obligation_type,
       coalesce(state, ''), coalesce(payer, ''), status
from obligations
where status in ('pending','queued','in_progress','exception')
  and deleted_at is null
"""

#: Open statuses an engine run may close when the roster no longer implies the
#: duty. Deliberately only the UNSTARTED ones: an ``in_progress`` obligation is
#: work a delivery associate has picked up, and an ``exception`` is a standing
#: finding a QA specialist must resolve -- yanking either out from under a human
#: loses context, so those are left for a person to close when they see the
#: affiliation ended. A closed obligation is soft-deleted, never hard-deleted:
#: the row stays for the audit trail (PRD 1.2).
CLOSEABLE_ON_ROSTER_SHRINK: frozenset[str] = frozenset({"pending", "queued"})


def obligations_to_close(
    planned_keys: set[tuple[Any, ...]], open_rows: Sequence[Sequence[Any]]
) -> list[UUID]:
    """Return the ids of open obligations the roster no longer implies.

    A duty is closed when its open-duty key is absent from this run's plan --
    the affiliation ended, the licence was removed, the payer dropped -- and it
    has not been started. Rows in :data:`CLOSEABLE_ON_ROSTER_SHRINK` only; an
    in-progress or exception row is left for a human.

    Args:
        planned_keys: The set of ``ObligationSpec.key`` this run planned.
        open_rows: ``(id, clinician_id, practice_id, obligation_type,
            coalesce(state,''), coalesce(payer,''), status)`` for every open
            obligation.

    Returns:
        The ids to soft-delete.
    """
    to_close: list[UUID] = []
    for row in open_rows:
        key = (row[1], row[2], row[3], str(row[4]).strip(), row[5])
        if key not in planned_keys and row[6] in CLOSEABLE_ON_ROSTER_SHRINK:
            to_close.append(row[0])
    return to_close


def load_roster(conn: psycopg.Connection, as_of: date) -> Roster:
    """Read every table the engine needs, in a handful of queries.

    Args:
        conn: Open connection.
        as_of: The run date. Affiliations are filtered against it.

    Returns:
        A :class:`Roster` snapshot. Planning never touches the database again.
    """
    params = {"as_of": as_of}
    affiliations = [
        Affiliation(clinician_id=r[0], practice_id=r[1], is_billing=bool(r[2]), tier=r[3])
        for r in fetch_all(conn, _QUERY_AFFILIATIONS, params)
    ]
    licenses = [
        License(
            clinician_id=r[0],
            state=str(r[1]).strip(),
            license_type=r[2],
            status=r[3],
            expiry_date=r[4],
            issue_date=r[5],
        )
        for r in fetch_all(conn, _QUERY_LICENSES)
    ]
    registrations = [
        Registration(
            clinician_id=r[0],
            kind=r[1],
            state=str(r[2]).strip() if r[2] is not None else None,
            status=r[3],
            expiry_date=r[4],
        )
        for r in fetch_all(conn, _QUERY_REGISTRATIONS)
    ]
    enrollments = [
        Enrollment(
            clinician_id=r[0],
            practice_id=r[1],
            payer=r[2],
            status=r[3],
            effective_date=r[4],
            revalidation_due=r[5],
            verified_at=r[6],
        )
        for r in fetch_all(conn, _QUERY_ENROLLMENTS)
    ]
    privileges = [
        Privilege(clinician_id=r[0], facility_name=r[1], reappointment_due=r[2], granted_date=r[3])
        for r in fetch_all(conn, _QUERY_PRIVILEGES)
    ]
    ce_records = [
        CeRecord(
            clinician_id=r[0],
            state=str(r[1]).strip() if r[1] is not None else None,
            cycle_start=r[2],
            cycle_end=r[3],
            topic=r[4],
            hours=r[5],
        )
        for r in fetch_all(conn, _QUERY_CE)
    ]
    sanctions = [
        Sanction(clinician_id=r[0], source=r[1], action_date=r[2], reinstated_date=r[3])
        for r in fetch_all(conn, _QUERY_SANCTIONS)
    ]

    rule_sets: dict[tuple[str, str], dict[str, Rule]] = {}
    for row in fetch_all(conn, _QUERY_REQUIREMENTS):
        state = str(row[0]).strip()
        license_type = row[1]
        rule = Rule(
            state=state,
            license_type=license_type,
            field_key=row[2],
            value_num=row[3],
            value_bool=row[4],
            value_text=row[5],
            value_json=row[6],
            version=int(row[7]),
        )
        rule_sets.setdefault((state, license_type), {})[rule.field_key] = rule

    return Roster(
        as_of=as_of,
        affiliations=affiliations,
        licenses=licenses,
        registrations=registrations,
        enrollments=enrollments,
        privileges=privileges,
        ce_records=ce_records,
        sanctions=sanctions,
        rule_sets={key: RuleSet(key[0], key[1], rules) for key, rules in rule_sets.items()},
    )


@dataclass
class EngineResult:
    """What one engine run did, or would have done.

    Attributes:
        as_of: The run date.
        dry_run: True when nothing was written.
        planned: Every spec the roster implied, in priority order.
        inserted: Obligations created.
        updated: Open obligations whose date, window, severity or rule version
            moved. This is the rule-change path.
        unchanged: Open obligations the run confirmed and left alone.
        closed: Open, unstarted obligations soft-deleted because the roster no
            longer implies them (an affiliation ended, a licence was removed).
        by_type: Planned count per obligation type.
        by_severity: Planned count per severity.
    """

    as_of: date
    dry_run: bool
    planned: list[ObligationSpec] = field(default_factory=list)
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    closed: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """A JSON-serializable summary, for the CLI and for instrumentation."""
        return {
            "as_of": self.as_of.isoformat(),
            "dry_run": self.dry_run,
            "planned": len(self.planned),
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "closed": self.closed,
            "by_type": dict(sorted(self.by_type.items())),
            "by_severity": dict(sorted(self.by_severity.items())),
        }


def run(
    conn: psycopg.Connection,
    *,
    as_of: date | None = None,
    dry_run: bool = False,
    generated_at: datetime | None = None,
) -> EngineResult:
    """Run the engine against ``conn``.

    Args:
        conn: Open connection. The caller owns it; the write runs in a nested
            transaction so a failed run leaves no partial calendar.
        as_of: Run date. Defaults to today in UTC.
        dry_run: Plan and report, write nothing.
        generated_at: Value for ``obligations.generated_at``. Defaults to now.

    Returns:
        An :class:`EngineResult`.
    """
    as_of = as_of or datetime.now(UTC).date()
    generated_at = generated_at or datetime.now(UTC)

    roster = load_roster(conn, as_of)
    specs = sort_by_priority(plan(roster), as_of)
    LOGGER.info(
        "planned %s obligations for %s affiliations as of %s",
        len(specs),
        len(roster.affiliations),
        as_of,
    )

    result = EngineResult(as_of=as_of, dry_run=dry_run, planned=specs)
    for spec in specs:
        result.by_type[spec.obligation_type] = result.by_type.get(spec.obligation_type, 0) + 1
        result.by_severity[spec.severity] = result.by_severity.get(spec.severity, 0) + 1

    if dry_run:
        _classify_dry_run(conn, specs, result)
        LOGGER.warning("DRY RUN: nothing written; %s", result.summary())
        return result

    with transaction(conn), conn.cursor() as cur:
        for spec in specs:
            cur.execute(UPSERT_SQL, spec.parameters(generated_at))
            row = cur.fetchone()
            if row is None:
                result.unchanged += 1
            elif row[1]:
                result.inserted += 1
            else:
                result.updated += 1

        # Close what the roster no longer implies. Read AFTER the upserts, so
        # every duty this run planned is already open and none is closed by
        # mistake; a key that is still absent belongs to a departed affiliation.
        planned_keys = {spec.key for spec in specs}
        open_rows = fetch_all(conn, _QUERY_OPEN_OBLIGATION_IDS)
        close_ids = obligations_to_close(planned_keys, open_rows)
        if close_ids:
            cur.execute(
                "update obligations set deleted_at = %s where id = any(%s) and deleted_at is null",
                (generated_at, close_ids),
            )
            result.closed = cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(close_ids)
    LOGGER.info("engine run complete: %s", result.summary())
    return result


def _classify_dry_run(
    conn: psycopg.Connection, specs: Sequence[ObligationSpec], result: EngineResult
) -> None:
    """Fill in would-insert / would-update / unchanged without writing."""
    existing: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    for row in fetch_all(conn, _QUERY_OPEN_OBLIGATIONS):
        existing[(row[0], row[1], row[2], str(row[3]).strip(), row[4])] = (
            row[5],
            row[6],
            row[7],
            row[8],
        )
    for spec in specs:
        current = existing.get(spec.key)
        if current is None:
            result.inserted += 1
        elif current != (spec.due_date, spec.window_opens, spec.severity, spec.rule_version):
            result.updated += 1
        else:
            result.unchanged += 1

    # Would-close: open, unstarted duties this plan no longer implies.
    planned_keys = {spec.key for spec in specs}
    open_rows = fetch_all(conn, _QUERY_OPEN_OBLIGATION_IDS)
    result.closed = len(obligations_to_close(planned_keys, open_rows))


def run_engine(
    settings: Settings | None = None,
    *,
    as_of: date | None = None,
    dry_run: bool = False,
) -> EngineResult:
    """Open a connection, run the engine, commit, close.

    The form a scheduler calls. ``run`` is the form a test calls.
    """
    conn = connect(settings)
    try:
        result = run(conn, as_of=as_of, dry_run=dry_run)
        if not dry_run:
            conn.commit()
        return result
    finally:
        conn.close()
