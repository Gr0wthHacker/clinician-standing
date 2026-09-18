"""The classifier (PRD section 8) -- the part the margin depends on.

Every pending obligation passes through here before a human sees anything, and
lands in exactly one of three places (PRD 4, 8):

* **auto_cleared** -- all seven PRD 8.1 conditions hold. Logged with its
  evidence, never shown to a person.
* **queued** -- the action queue: deterministic work with a known procedure, a
  renewal inside its window, pre-filled for a delivery associate.
* **exception** -- the QA queue, tagged with one of the eight reason codes in
  PRD 8.3.

The auto-clear rate this produces is, in the PRD's words, "the single metric
that determines whether this business works." :class:`ClassifierResult` reports
it every run, so it is instrumented from the first week (PRD 1.1) -- and today,
with only federal sources and Nursys wired, it reads honestly low until more
primary sources land, which is the point of measuring it rather than assuming
it.

The module is split like the engine: :func:`classify` is a pure decision over
:class:`ObligationFacts` and is exhaustively unit-tested; :func:`run` gathers
those facts from the database and applies the decisions.

PRD 8.1 -- all must hold to auto-clear:
    1. a primary-source assertion exists (is_primary_source, attesting the type)
    2. fetched within that source's freshness SLA
    3. identity matched on a strong single key (NPI, or licence number + state)
    4. no conflicting assertion from any other source
    5. the rule version used is is_current
    6. no open requirement_conflicts for that state, licence type and field
    7. severity is routine
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import psycopg

from .config import Settings
from .db import connect, fetch_all, transaction
from .engine import DUTY_FIELD_KEYS

__all__ = [
    "DOCUMENT_TYPES",
    "PORTAL_TYPES",
    "REASON_CODES",
    "RENEWAL_TYPES",
    "SCREEN_TYPES",
    "STRONG_MATCH_METHODS",
    "ClassifierResult",
    "Decision",
    "ObligationFacts",
    "classify",
    "generating_field",
    "run",
    "run_classifier",
]

LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------- outcomes
OUTCOME_AUTO = "auto_cleared"
OUTCOME_QUEUED = "queued"
OUTCOME_EXCEPTION = "exception"
OUTCOME_SKIP = "skip"

# Reason codes, exactly the set 0005_obligations.sql enforces (PRD 8.3).
IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
SOURCE_STALE = "SOURCE_STALE"
RULE_UNCERTAIN = "RULE_UNCERTAIN"
HIGH_CONSEQUENCE = "HIGH_CONSEQUENCE"
PORTAL_REQUIRED = "PORTAL_REQUIRED"
DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
TERMS_LAPSED = "TERMS_LAPSED"

REASON_CODES: frozenset[str] = frozenset(
    {
        IDENTITY_AMBIGUOUS,
        SOURCE_CONFLICT,
        SOURCE_STALE,
        RULE_UNCERTAIN,
        HIGH_CONSEQUENCE,
        PORTAL_REQUIRED,
        DOCUMENT_REQUIRED,
        TERMS_LAPSED,
    }
)

# How the verified work of each obligation type is done, which decides where a
# verified-but-actionable duty goes.
RENEWAL_TYPES: frozenset[str] = frozenset({"license_renewal", "csr_renewal", "dea_renewal"})
#: Revalidation is done inside a payer portal, which is a non-goal to automate
#: (PRD 2), so an actionable one is a PORTAL_REQUIRED exception, not action-queue.
PORTAL_TYPES: frozenset[str] = frozenset({"medicare_revalidation", "payer_revalidation"})
#: CE and privileging are attested by a document only the clinician can supply
#: (0003: their evidence_id is nullable), so an unverified one is DOCUMENT_REQUIRED.
DOCUMENT_TYPES: frozenset[str] = frozenset({"ce_cycle", "privilege_reappointment"})
#: A screen (exclusion) is satisfied by a clean, fresh result, not by manual work.
SCREEN_TYPES: frozenset[str] = frozenset({"exclusion_screen"})

#: match_keys.method values that are a strong single identity key (PRD 8.1
#: condition 3). Anything else is not enough to auto-clear against a named person.
STRONG_MATCH_METHODS: frozenset[str] = frozenset({"npi_exact", "nursys_ncsbn", "license_state"})


def generating_field(obligation_type: str) -> str | None:
    """The requirements field_key that generates ``obligation_type``.

    Used to check condition 5 (is_current) and condition 6 (open conflicts)
    against the rules plane. It is the first key in the duty's field tuple, the
    same one :func:`~clinician_standing.engine.RuleSet.version_for` treats as the
    generating rule.
    """
    keys = DUTY_FIELD_KEYS.get(obligation_type, ())
    return keys[0] if keys else None


# ===========================================================================
# The decision -- pure
# ===========================================================================
@dataclass(frozen=True)
class Decision:
    """Where an obligation goes, and why.

    Attributes:
        outcome: ``auto_cleared`` | ``queued`` | ``exception`` | ``skip``.
        reason_code: The PRD 8.3 code, set only for an ``exception``.
        detail: A short human-readable cause, for the exception row and the log.
    """

    outcome: str
    reason_code: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class ObligationFacts:
    """Everything :func:`classify` needs about one obligation, gathered once.

    Attributes:
        obligation_id: The row being classified.
        obligation_type: Its type (drives the routing sets).
        severity: routine | elevated | critical (PRD 8.1 condition 7).
        actionable: True when the obligation's window has opened (there is work
            to do now), i.e. window_opens is set and on/before the run date.
        has_primary_evidence: A primary source attesting this type matched the
            clinician (condition 1).
        evidence_fresh: That assertion is inside its freshness SLA (condition 2).
        strong_single_match: It matched on a strong single key (condition 3).
        has_conflict: Another primary source disagrees (condition 4).
        rule_current: The generating rule version is is_current, or the duty
            rests on a default with no cited rule (condition 5).
        open_conflict: An open requirement_conflicts row covers this rule
            (condition 6).
        exclusion_hit: An exclusion or discipline hit stands for this clinician.
        lapsed_while_billing: The licence behind this duty is lapsed and the
            clinician bills under the practice.
        terms_lapsed: A scrape source feeding this duty has a terms review over
            180 days old (PRD 6.4, 13).
        evidence_id: The supporting evidence to stamp on an auto-cleared row.
    """

    obligation_id: UUID
    obligation_type: str
    severity: str
    actionable: bool = False
    has_primary_evidence: bool = False
    evidence_fresh: bool = False
    strong_single_match: bool = False
    has_conflict: bool = False
    rule_current: bool = True
    open_conflict: bool = False
    exclusion_hit: bool = False
    lapsed_while_billing: bool = False
    terms_lapsed: bool = False
    evidence_id: UUID | None = None


def classify(f: ObligationFacts) -> Decision:
    """Decide where one obligation goes. Pure; the heart of PRD section 8.

    The seven PRD 8.1 conditions must all hold to auto-clear. A failing condition
    routes to the exception or action queue with the most specific reason code,
    checked in an order that puts the highest-consequence and least-recoverable
    causes first.

    Args:
        f: The gathered facts.

    Returns:
        A :class:`Decision`. ``skip`` means leave the obligation pending -- used
        when the generating rule was superseded and the engine will regenerate
        the duty on its next run.
    """
    # A scrape source with lapsed terms fails the whole run closed (PRD 6.4, 13).
    if f.terms_lapsed:
        return Decision(OUTCOME_EXCEPTION, TERMS_LAPSED, "source terms review over 180 days old")

    # HIGH_CONSEQUENCE (PRD 8.3): the findings a human must see the same day.
    if f.exclusion_hit:
        return Decision(OUTCOME_EXCEPTION, HIGH_CONSEQUENCE, "exclusion or discipline hit")
    if f.lapsed_while_billing:
        return Decision(OUTCOME_EXCEPTION, HIGH_CONSEQUENCE, "licence lapsed while billing")

    # Condition 5: a duty generated by a superseded rule is stale. Leave it
    # pending rather than acting on it; the engine refreshes rule_version.
    if not f.rule_current:
        return Decision(OUTCOME_SKIP, None, "rule version superseded; awaiting engine regeneration")

    # Condition 6: an open conflict about the rule itself.
    if f.open_conflict:
        return Decision(OUTCOME_EXCEPTION, RULE_UNCERTAIN, "open requirement_conflicts")

    # Condition 1: without a primary-source assertion nothing can be cleared. The
    # unverified duty is work, routed by how that work is done.
    if not f.has_primary_evidence:
        if f.obligation_type in DOCUMENT_TYPES:
            return Decision(OUTCOME_EXCEPTION, DOCUMENT_REQUIRED, "no assertion; document required")
        if f.obligation_type in PORTAL_TYPES:
            return Decision(OUTCOME_EXCEPTION, PORTAL_REQUIRED, "no assertion; portal verification")
        return Decision(OUTCOME_QUEUED, None, "no primary-source assertion yet; verify")

    # Condition 2.
    if not f.evidence_fresh:
        return Decision(OUTCOME_EXCEPTION, SOURCE_STALE, "assertion outside the freshness SLA")

    # Condition 3.
    if not f.strong_single_match:
        return Decision(OUTCOME_EXCEPTION, IDENTITY_AMBIGUOUS, "no strong single identity match")

    # Condition 4.
    if f.has_conflict:
        return Decision(OUTCOME_EXCEPTION, SOURCE_CONFLICT, "primary sources disagree")

    # Condition 7: a non-routine duty is real work or real urgency, never cleared.
    if f.severity != "routine":
        if f.obligation_type in PORTAL_TYPES:
            return Decision(OUTCOME_EXCEPTION, PORTAL_REQUIRED, f"{f.severity} revalidation")
        return Decision(OUTCOME_QUEUED, None, f"{f.severity}: actionable work")

    # All seven hold and severity is routine. A clean, fresh screen is done. A
    # renewal whose window has opened is deterministic action-queue work. A
    # revalidation is portal work. Anything not yet actionable is confirmed.
    if f.obligation_type in SCREEN_TYPES:
        return Decision(OUTCOME_AUTO, None, "screen clean and fresh")
    if f.actionable:
        if f.obligation_type in PORTAL_TYPES:
            return Decision(OUTCOME_EXCEPTION, PORTAL_REQUIRED, "revalidation window open; portal")
        return Decision(OUTCOME_QUEUED, None, "window open; deterministic renewal work")
    return Decision(OUTCOME_AUTO, None, "verified fresh; nothing due")


# ===========================================================================
# Result
# ===========================================================================
@dataclass
class ClassifierResult:
    """What one classifier run did, and the auto-clear rate it observed."""

    as_of: date
    dry_run: bool
    by_outcome: dict[str, int] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)

    def record(self, decision: Decision) -> None:
        """Tally one decision."""
        self.by_outcome[decision.outcome] = self.by_outcome.get(decision.outcome, 0) + 1
        if decision.reason_code:
            self.by_reason[decision.reason_code] = self.by_reason.get(decision.reason_code, 0) + 1

    @property
    def decided(self) -> int:
        """Obligations that reached a terminal routing (not skipped)."""
        return sum(v for k, v in self.by_outcome.items() if k != OUTCOME_SKIP)

    @property
    def auto_clear_rate(self) -> float | None:
        """auto_cleared / (auto_cleared + queued + exception), or None if empty.

        The single metric the margin rests on (PRD 1.1). Skipped obligations are
        excluded because they were not routed.
        """
        decided = self.decided
        if decided == 0:
            return None
        return round(self.by_outcome.get(OUTCOME_AUTO, 0) / decided, 4)

    def summary(self) -> dict[str, Any]:
        """A JSON-serializable summary for the CLI and instrumentation."""
        return {
            "as_of": self.as_of.isoformat(),
            "dry_run": self.dry_run,
            "by_outcome": dict(sorted(self.by_outcome.items())),
            "by_reason": dict(sorted(self.by_reason.items())),
            "decided": self.decided,
            "auto_clear_rate": self.auto_clear_rate,
        }


# ===========================================================================
# Gathering the facts -- the database half
# ===========================================================================
_QUERY_PENDING = """
select id, clinician_id, practice_id, obligation_type, state, payer,
       severity, window_opens, rule_version
from obligations
where status = 'pending' and deleted_at is null
order by id
"""

# One primary-source assertion per credential row, expanded to every obligation
# type its source attests to, so a single row can support several duties.
_QUERY_SUPPORT = """
with cred as (
    select clinician_id, state, evidence_id from licenses where deleted_at is null
    union all
    select clinician_id, state, evidence_id from registrations where deleted_at is null
    union all
    select clinician_id, null::char(2), evidence_id from enrollments where deleted_at is null
    union all
    select clinician_id, null::char(2), evidence_id from sanctions where deleted_at is null
)
select cr.clinician_id, cr.state, ot as obligation_type,
       e.id, e.match_keys, (e.freshness_expires_at > %(now)s) as fresh, e.fetched_at,
       e.source_key
from cred cr
join evidence e on e.id = cr.evidence_id and e.deleted_at is null
join sources s on s.key = e.source_key
cross join lateral unnest(s.attests_obligation_types) as ot
where s.is_primary_source
"""

_QUERY_CURRENT_RULES = """
select state, field_key, array_agg(distinct version) as versions
from requirements
where is_current and deleted_at is null
group by state, field_key
"""

_QUERY_OPEN_CONFLICTS = """
select distinct r.state, r.field_key
from requirement_conflicts c
join requirements r on r.id = c.requirement_id
where (c.resolution is null or c.resolution = 'unresolved') and c.deleted_at is null
"""

_QUERY_EXCLUSIONS = """
select distinct clinician_id
from sanctions
where deleted_at is null
  and (reinstated_date is null or reinstated_date > %(as_of)s)
"""

# Licence status per clinician+state, for lapse-while-billing and for the
# same-state status-divergence proxy for SOURCE_CONFLICT.
_QUERY_LICENSES = """
select l.clinician_id, l.state, l.status, l.expiry_date,
       bool_or(coalesce(a.is_billing, false)) as billing
from licenses l
left join affiliations a
  on a.clinician_id = l.clinician_id and a.deleted_at is null
 and (a.end_date is null or a.end_date > %(as_of)s)
 and (a.start_date is null or a.start_date <= %(as_of)s)
where l.deleted_at is null
group by l.clinician_id, l.state, l.status, l.expiry_date
"""

_LAPSED_STATUSES: frozenset[str] = frozenset({"expired", "lapsed", "suspended", "revoked"})
#: State-scoped duties a lapsed licence makes high-consequence.
_LAPSE_SENSITIVE: frozenset[str] = frozenset({"license_renewal", "csr_renewal", "ce_cycle"})

# A screen (exclusion) is satisfied roster-wide by a fresh file, not by a
# per-clinician credential row: a CLEAN clinician has no sanctions row at all, so
# support keyed on a credential would find nothing and wrongly queue every clean
# screen. This gives, per obligation type a primary source attests to, whether
# that source has a fresh assertion and the evidence id to cite -- for
# exclusion_screen, the latest fresh OIG LEIE / SAM file. A hit is handled
# separately (exclusion_hit); this is what lets a clean screen auto-clear.
_QUERY_SCREEN_COVERAGE = """
select ot as obligation_type, e.id as evidence_id,
       (e.freshness_expires_at > %(now)s) as fresh
from sources s
cross join lateral unnest(s.attests_obligation_types) as ot
join lateral (
    select id, freshness_expires_at
    from evidence
    where source_key = s.key and deleted_at is null
    order by fetched_at desc
    limit 1
) e on true
where s.is_primary_source
"""


def _is_strong_single(match_keys: Any) -> bool:
    """True when match_keys describes a strong single identity match (cond 3)."""
    if not isinstance(match_keys, Mapping):
        return False
    method = str(match_keys.get("method", ""))
    if method not in STRONG_MATCH_METHODS:
        return False
    confidence = match_keys.get("match_confidence")
    return confidence is None or float(confidence) >= 1.0


def _gather(conn: psycopg.Connection, as_of: date) -> list[ObligationFacts]:
    """Read the database and build one :class:`ObligationFacts` per pending row."""
    now = datetime.combine(as_of, datetime.min.time(), tzinfo=UTC)

    # Best (freshest) primary support per (clinician, type, state); collect the
    # set of source keys and statuses that back the same key, for conflict.
    support: dict[tuple[UUID, str, str | None], dict[str, Any]] = {}
    for r in fetch_all(conn, _QUERY_SUPPORT, {"now": now}):
        clinician_id, state, otype, evidence_id, match_keys, fresh, fetched_at, source_key = r
        key = (clinician_id, otype, state)
        entry = support.setdefault(key, {"sources": set(), "best": None})
        entry["sources"].add(source_key)
        best = entry["best"]
        if best is None or fetched_at > best["fetched_at"]:
            entry["best"] = {
                "evidence_id": evidence_id,
                "fresh": bool(fresh),
                "strong": _is_strong_single(match_keys),
                "fetched_at": fetched_at,
            }

    current_rules = {
        (str(r[0]).strip(), r[1]): set(r[2]) for r in fetch_all(conn, _QUERY_CURRENT_RULES)
    }
    open_conflicts = {
        (str(r[0]).strip(), r[1]) for r in fetch_all(conn, _QUERY_OPEN_CONFLICTS)
    }
    excluded = {r[0] for r in fetch_all(conn, _QUERY_EXCLUSIONS, {"as_of": as_of})}

    # Per-type roster-wide screen coverage: the evidence id of the latest fresh
    # primary assertion for each attested type. Keeps only fresh ones.
    screen_coverage: dict[str, UUID] = {}
    for otype, evidence_id, fresh in fetch_all(conn, _QUERY_SCREEN_COVERAGE, {"now": now}):
        if fresh:
            screen_coverage[otype] = evidence_id

    lapsed_billing: dict[tuple[UUID, str], bool] = {}
    status_by_key: dict[tuple[UUID, str], set[str]] = {}
    for clinician_id, state, status, expiry, billing in fetch_all(
        conn, _QUERY_LICENSES, {"as_of": as_of}
    ):
        st = str(state).strip()
        is_lapsed = status in _LAPSED_STATUSES or (expiry is not None and expiry < as_of)
        if is_lapsed and billing:
            lapsed_billing[(clinician_id, st)] = True
        status_by_key.setdefault((clinician_id, st), set()).add(status)

    facts: list[ObligationFacts] = []
    for row in fetch_all(conn, _QUERY_PENDING):
        facts.append(
            _facts_for(
                row,
                as_of=as_of,
                support=support,
                current_rules=current_rules,
                open_conflicts=open_conflicts,
                excluded=excluded,
                lapsed_billing=lapsed_billing,
                status_by_key=status_by_key,
                screen_coverage=screen_coverage,
            )
        )
    return facts


def _facts_for(
    row: tuple[Any, ...],
    *,
    as_of: date,
    support: dict[tuple[UUID, str, str | None], dict[str, Any]],
    current_rules: dict[tuple[str, str], set[int]],
    open_conflicts: set[tuple[str, str]],
    excluded: set[UUID],
    lapsed_billing: dict[tuple[UUID, str], bool],
    status_by_key: dict[tuple[UUID, str], set[str]],
    screen_coverage: dict[str, UUID],
) -> ObligationFacts:
    """Assemble one obligation's facts from the preloaded maps."""
    (obligation_id, clinician_id, _practice_id, otype, state, _payer,
     severity, window_opens, rule_version) = row
    state = str(state).strip() if state is not None else None

    entry = support.get((clinician_id, otype, state)) or support.get((clinician_id, otype, None))
    best = entry["best"] if entry else None
    sources = entry["sources"] if entry else set()

    if otype in SCREEN_TYPES:
        # A clean screen is verified by a fresh roster-wide file (screen_coverage
        # holds only fresh entries), matched by NPI, with no conflicting source.
        screen_evidence = screen_coverage.get(otype)
        has_primary = screen_evidence is not None
        evidence_fresh = has_primary
        strong_single = has_primary
        has_conflict = False
        evidence_id = screen_evidence
    else:
        has_primary = best is not None
        evidence_fresh = bool(best and best["fresh"])
        strong_single = bool(best and best["strong"])
        key_cs_conflict = (clinician_id, state) if state is not None else None
        divergent = bool(key_cs_conflict and len(status_by_key.get(key_cs_conflict, set())) > 1)
        has_conflict = len(sources) > 1 and divergent
        evidence_id = best["evidence_id"] if best else None

    gen_field = generating_field(otype)
    if rule_version is None or gen_field is None:
        rule_current = True  # a default-derived duty has no cited rule to be stale
    elif state is not None:
        rule_current = rule_version in current_rules.get((state, gen_field), set())
    else:
        rule_current = True  # federal/payer duties are not state-rule-scoped here

    key_cs = (clinician_id, state) if state is not None else None

    return ObligationFacts(
        obligation_id=obligation_id,
        obligation_type=otype,
        severity=severity,
        actionable=window_opens is not None and window_opens <= as_of,
        has_primary_evidence=has_primary,
        evidence_fresh=evidence_fresh,
        strong_single_match=strong_single,
        has_conflict=has_conflict,
        rule_current=rule_current,
        open_conflict=(state, gen_field) in open_conflicts if state and gen_field else False,
        exclusion_hit=(otype == "exclusion_screen" and clinician_id in excluded),
        lapsed_while_billing=(
            otype in _LAPSE_SENSITIVE and bool(key_cs and lapsed_billing.get(key_cs))
        ),
        evidence_id=evidence_id,
    )


# ===========================================================================
# Applying the decisions
# ===========================================================================
_UPDATE_STATUS = """
update obligations set status = %(status)s, evidence_id = %(evidence_id)s
where id = %(id)s and status = 'pending'
"""

_INSERT_EXCEPTION = """
insert into exceptions (obligation_id, reason_code, detail, raised_at)
values (%(obligation_id)s, %(reason_code)s, %(detail)s, %(raised_at)s)
"""


def run(
    conn: psycopg.Connection,
    *,
    as_of: date | None = None,
    dry_run: bool = False,
    raised_at: datetime | None = None,
) -> ClassifierResult:
    """Classify every pending obligation and route it (PRD section 8).

    Args:
        conn: Open connection; the caller owns it. The writes run in a nested
            transaction so a failed run leaves no half-classified queue.
        as_of: Run date, for freshness and window arithmetic. Defaults to today.
        dry_run: Classify and report; write nothing.
        raised_at: Timestamp for exception rows; defaults to now.

    Returns:
        A :class:`ClassifierResult`, including the observed auto-clear rate.
    """
    as_of = as_of or datetime.now(UTC).date()
    raised_at = raised_at or datetime.now(UTC)
    facts = _gather(conn, as_of)
    result = ClassifierResult(as_of=as_of, dry_run=dry_run)

    decisions = [(f, classify(f)) for f in facts]
    for _f, decision in decisions:
        result.record(decision)

    if dry_run:
        LOGGER.warning("DRY RUN: nothing written; %s", result.summary())
        return result

    with transaction(conn), conn.cursor() as cur:
        for f, decision in decisions:
            if decision.outcome == OUTCOME_SKIP:
                continue
            cur.execute(
                _UPDATE_STATUS,
                {
                    "id": f.obligation_id,
                    # outcome is one of auto_cleared | queued | exception, all of
                    # which are valid obligations.status values (0005).
                    "status": decision.outcome,
                    # Only an auto-cleared row records the evidence it cleared on.
                    "evidence_id": f.evidence_id if decision.outcome == OUTCOME_AUTO else None,
                },
            )
            if decision.outcome == OUTCOME_EXCEPTION:
                cur.execute(
                    _INSERT_EXCEPTION,
                    {
                        "obligation_id": f.obligation_id,
                        "reason_code": decision.reason_code,
                        "detail": decision.detail,
                        "raised_at": raised_at,
                    },
                )
    LOGGER.info("classifier run complete: %s", result.summary())
    return result


def run_classifier(
    settings: Settings | None = None, *, as_of: date | None = None, dry_run: bool = False
) -> ClassifierResult:
    """Open a connection, classify, commit, close. The form a scheduler calls."""
    conn = connect(settings)
    try:
        result = run(conn, as_of=as_of, dry_run=dry_run)
        if not dry_run:
            conn.commit()
        return result
    finally:
        conn.close()
