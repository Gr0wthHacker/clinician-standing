"""The free roster audit (PRD section 9).

The sales motion. Given nothing but a CMS group PAC ID, this module reads the
federal data already ingested and produces a findings document: exclusion and
sanction screen, Medicare enrollment reality, directory accuracy, roster
composition, and a severity-ordered summary. It asks the prospect for nothing,
touches no client system, and makes no outbound request of its own.

Three rules govern everything below, and they are the reason the artifact is
worth anything at all.

**A clean screen is reported as what it is, not as what a prospect would like
to hear.** NPI coverage in the OIG LEIE file is about 10%; name-and-date-of-
birth matching is not enabled in this build. So a roster with no hits has not
been cleared -- it has been checked against roughly a tenth of the file. Every
exclusion result in this module states the count of records it could not screen
alongside the count it could. A false reassurance here is the single worst
output this system can produce, and it would be produced by omission, not by
error.

**Every finding carries its source and the date that source was fetched.** The
document is a compliance artifact. An assertion without a citation and a
timestamp is worth less than no assertion, because it invites reliance it
cannot support.

**Where the data does not support a finding, the section says so.** "We could
not assess X because Y" is a legitimate output and it appears in its own
numbered section rather than being dropped. A quiet omission reads as a clean
result.

Interface::

    result = audit_practice("7911259619")
    print(render_markdown(result))

or from the command line::

    python -m clinician_standing audit 7911259619 --format html
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import psycopg

from .config import Settings
from .db import connect, fetch_all, table_exists

__all__ = [
    "AuditResult",
    "DirectoryAccuracy",
    "EnrollmentReality",
    "ExclusionScreen",
    "Finding",
    "PracticeNotFound",
    "PracticeProfile",
    "RosterComposition",
    "Severity",
    "SourceState",
    "audit_practice",
    "render_html",
    "render_json",
    "render_markdown",
]


# ---------------------------------------------------------------------------
# Regulatory constants
# ---------------------------------------------------------------------------

#: 42 CFR 424.521(a): a physician, non-physician practitioner, physician
#: organization or non-physician organization may bill retrospectively for
#: services furnished up to 30 days before its effective date of enrollment.
#: When a revalidation lapse ends in deactivation, this is the whole of the
#: gap that can be recovered on reactivation. Everything earlier is unbillable.
RETROSPECTIVE_BILLING_DAYS = 30

#: The citation, printed next to every number derived from it.
RETROSPECTIVE_BILLING_CITE = "42 CFR 424.521(a)"

#: A revalidation due inside this window is close enough to act on but is not
#: yet a lapse. CMS mails the revalidation request 2-3 months ahead.
DUE_SOON_DAYS = 180

#: Sources this audit reads or reports on, in the order the document names them.
AUDIT_SOURCE_KEYS: tuple[str, ...] = (
    "cms_dac",
    "cms_revalidation",
    "oig_leie",
    "sam_gov",
    "nppes",
)


class Severity(StrEnum):
    """Finding severity, ordered worst first by :data:`SEVERITY_ORDER`."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"
    NOT_ASSESSED = "not_assessed"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 4,
    Severity.NOT_ASSESSED: 5,
}


class PracticeNotFound(LookupError):
    """No practice in the database carries the requested ``org_pac_id``."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceState:
    """What the database knows about one registered source.

    Attributes:
        key: Registry key, e.g. ``oig_leie``.
        display_name: Human name as the registry spells it.
        cadence: Publication cadence from the registry.
        freshness_sla_days: How old an assertion from this source may be.
        enabled: Whether the connector is turned on.
        is_primary_source: Registry flag (PRD 5.5).
        fetched_at: ``fetched_at`` of the newest evidence row, or None.
        expires_at: ``freshness_expires_at`` of that row, or None.
        stale: True when that row is past its freshness horizon.
        age_days: Age of that row in days, or None.
        last_run_at / last_run_status: Newest ``source_runs`` entry.
        parsed: The evidence row's ``parsed`` payload (file-level statistics).
    """

    key: str
    display_name: str | None
    cadence: str | None
    freshness_sla_days: int
    enabled: bool
    is_primary_source: bool
    fetched_at: datetime | None
    expires_at: datetime | None
    stale: bool
    age_days: int | None
    last_run_at: datetime | None
    last_run_status: str | None
    parsed: dict[str, Any] = field(default_factory=dict)

    @property
    def ingested(self) -> bool:
        """True when at least one evidence row exists for this source."""
        return self.fetched_at is not None

    def citation(self) -> str:
        """One-line citation: name plus the date the snapshot was fetched."""
        name = self.display_name or self.key
        if self.fetched_at is None:
            return f"{name} (never ingested)"
        return f"{name}, fetched {self.fetched_at.date().isoformat()}"


@dataclass(frozen=True)
class Finding:
    """One thing the audit found, with its provenance.

    Attributes:
        key: Stable machine identifier, safe to diff across runs.
        severity: See :class:`Severity`.
        title: One line, stating the fact and its size.
        detail: The supporting sentences, including the caveats.
        source_keys: Registry keys the finding rests on.
        citations: Rendered "name, fetched YYYY-MM-DD" strings, one per source.
        quantity: The countable size of the finding, when it has one.
        rank: Emission order, used to break ties inside a severity.
    """

    key: str
    severity: Severity
    title: str
    detail: str
    source_keys: tuple[str, ...]
    citations: tuple[str, ...]
    quantity: int | None = None
    rank: int = 0

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """Worst first, then by emission order, then by key for stability.

        Deliberately not by ``quantity``: the quantities are in different
        units. A group revalidation 292 days overdue and one clinician matched
        to an exclusion are both critical, and ordering them by the larger
        number would put the days ahead of the exclusion. Emission order
        encodes the intended precedence instead, and exclusions are emitted
        first.
        """
        return (SEVERITY_ORDER[self.severity], self.rank, self.key)


@dataclass(frozen=True)
class PracticeProfile:
    """The practice as CMS holds it."""

    org_pac_id: str
    legal_name: str
    dba_name: str | None
    npi_org: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip: str | None
    phone: str | None

    def address_lines(self) -> list[str]:
        """The postal address as separate display lines."""
        lines = [line for line in (self.address_line1, self.address_line2) if line]
        locality = " ".join(p for p in (self.city, self.state) if p)
        if self.zip:
            locality = f"{locality} {format_zip(self.zip)}".strip()
        if locality:
            lines.append(locality)
        return lines


@dataclass(frozen=True)
class ClinicianRef:
    """A clinician on the roster, as the document names them."""

    npi: str
    name: str
    credential: str | None
    clinician_type: str
    primary_specialty: str | None


@dataclass(frozen=True)
class ExclusionRow:
    """One exclusion or sanction matched to a clinician on this roster."""

    clinician: ClinicianRef
    source: str
    action_type: str | None
    action_date: date | None
    description: str | None
    reinstated_date: date | None
    match_confidence: float | None
    evidence_source_key: str | None
    evidence_fetched_at: datetime | None

    @property
    def open(self) -> bool:
        """True when no reinstatement date is recorded."""
        return self.reinstated_date is None


@dataclass(frozen=True)
class ExclusionScreen:
    """Result of screening the roster against LEIE and SAM."""

    roster_size: int
    leie_screened: bool
    leie_records_total: int | None
    leie_records_with_npi: int | None
    leie_records_unscreened: int | None
    leie_name_dob_enabled: bool
    leie_source: SourceState | None
    sam_screened: bool
    sam_source: SourceState | None
    hits: tuple[ExclusionRow, ...]

    @property
    def open_hits(self) -> tuple[ExclusionRow, ...]:
        """Hits with no recorded reinstatement."""
        return tuple(h for h in self.hits if h.open)


@dataclass(frozen=True)
class RevalidationRow:
    """One clinician's Medicare revalidation position."""

    clinician: ClinicianRef
    status: str
    revalidation_due: date | None
    days_overdue: int | None
    days_until_due: int | None
    unbillable_days: int | None
    # False when the reassignment file points this clinician at the group but
    # the directory file does not list them there. They still represent the
    # group's exposure, so they are counted -- and marked, never quietly mixed in.
    on_roster: bool = True


@dataclass(frozen=True)
class EnrollmentReality:
    """Medicare enrollment as the CMS revalidation file states it."""

    source: SourceState | None
    group_due_date: date | None
    group_days_overdue: int | None
    group_state_known: bool
    group_note: str
    rows: tuple[RevalidationRow, ...]
    overdue: tuple[RevalidationRow, ...]
    due_soon: tuple[RevalidationRow, ...]
    no_due_date: tuple[RevalidationRow, ...]
    unenrolled: tuple[ClinicianRef, ...]
    unaffiliated: tuple[ClinicianRef, ...]

    @property
    def total_unbillable_days(self) -> int:
        """Clinician-days past due that no reactivation can recover."""
        return sum(r.unbillable_days or 0 for r in self.overdue)

    @property
    def max_days_overdue(self) -> int:
        """Longest lapse on the roster, in days."""
        return max((r.days_overdue or 0 for r in self.overdue), default=0)


@dataclass(frozen=True)
class OtherListing:
    """A second place CMS lists a clinician who is on this roster."""

    clinician: ClinicianRef
    org_pac_id: str | None
    legal_name: str
    city: str | None
    state: str | None


@dataclass(frozen=True)
class DirectoryAccuracy:
    """Directory record as CMS holds it, and what disagrees with it."""

    profile: PracticeProfile
    directory_source: SourceState | None
    missing_fields: tuple[str, ...]
    stale: bool
    stale_note: str | None
    other_listings: tuple[OtherListing, ...]
    taxonomy_assessed: bool
    taxonomy_note: str
    specialty_source_note: str


@dataclass(frozen=True)
class RosterComposition:
    """Who is on the roster."""

    total: int
    by_type: dict[str, int]
    physicians: int
    non_physicians: int
    specialties: tuple[tuple[str, int], ...]
    distinct_specialties: int
    states: tuple[tuple[str, int], ...]
    telehealth_assessed: bool
    telehealth_count: int | None
    telehealth_note: str
    source: SourceState | None


@dataclass(frozen=True)
class AuditResult:
    """Everything the free roster audit produced for one practice."""

    org_pac_id: str
    generated_at: datetime
    as_of: date
    practice: PracticeProfile
    roster: RosterComposition
    exclusions: ExclusionScreen
    enrollment: EnrollmentReality
    directory: DirectoryAccuracy
    findings: tuple[Finding, ...]
    sources: tuple[SourceState, ...]
    limitations: tuple[str, ...]

    @property
    def worst_severity(self) -> Severity:
        """The severity of the first finding, or informational when there are none."""
        return self.findings[0].severity if self.findings else Severity.INFORMATIONAL

    def counts_by_severity(self) -> dict[str, int]:
        """Number of findings at each severity, worst first."""
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_PRACTICE_SQL = """
select id, org_pac_id, npi_org, legal_name, dba_name, address_line1, address_line2,
       city, state, zip, phone
from practices
where org_pac_id = %(org_pac_id)s and deleted_at is null
"""

_ROSTER_SQL = """
select c.id, c.npi, c.first_name, c.last_name, c.credential, c.clinician_type,
       c.primary_specialty
from affiliations a
join clinicians c on c.id = a.clinician_id and c.deleted_at is null
where a.practice_id = %(practice_id)s
  and a.deleted_at is null
  and a.end_date is null
order by c.last_name nulls last, c.first_name nulls last, c.npi
"""

_ROSTER_TELEHEALTH_SQL = """
select count(*) filter (where c.telehealth)
from affiliations a
join clinicians c on c.id = a.clinician_id and c.deleted_at is null
where a.practice_id = %(practice_id)s and a.deleted_at is null and a.end_date is null
"""

_STATES_SQL = """
select p2.state, count(distinct c.id)
from affiliations a
join clinicians c on c.id = a.clinician_id and c.deleted_at is null
join affiliations a2 on a2.clinician_id = c.id and a2.end_date is null and a2.deleted_at is null
join practices p2 on p2.id = a2.practice_id and p2.deleted_at is null
where a.practice_id = %(practice_id)s and a.end_date is null and a.deleted_at is null
  and p2.state is not null
group by p2.state
order by 2 desc, 1
"""

_OTHER_LISTINGS_SQL = """
select c.npi, c.first_name, c.last_name, c.credential, c.clinician_type, c.primary_specialty,
       p2.org_pac_id, p2.legal_name, p2.city, p2.state
from affiliations a
join clinicians c on c.id = a.clinician_id and c.deleted_at is null
join affiliations a2 on a2.clinician_id = c.id and a2.end_date is null and a2.deleted_at is null
join practices p2 on p2.id = a2.practice_id and p2.deleted_at is null
where a.practice_id = %(practice_id)s and a.end_date is null and a.deleted_at is null
  and a2.practice_id <> %(practice_id)s
order by c.last_name nulls last, p2.legal_name
"""

_ENROLLMENTS_SQL = """
select c.npi, c.first_name, c.last_name, c.credential, c.clinician_type, c.primary_specialty,
       e.status, e.revalidation_due
from enrollments e
join clinicians c on c.id = e.clinician_id and c.deleted_at is null
where e.practice_id = %(practice_id)s
  and e.payer = 'medicare'
  and e.deleted_at is null
  and e.clinician_id is not null
order by e.revalidation_due nulls last, c.last_name nulls last
"""

# A group-level Medicare enrollment is an enrollments row for the practice with
# no clinician: it is the group's own revalidation, which is what the CMS
# revalidation file calls "Group Due Date". The cms_revalidation connector does
# not derive one today -- it writes only per-clinician reassignment rows -- so
# this query commonly returns nothing and the audit says so rather than guessing.
_GROUP_ENROLLMENT_SQL = """
select status, revalidation_due, effective_date
from enrollments
where practice_id = %(practice_id)s
  and clinician_id is null
  and payer = 'medicare'
  and deleted_at is null
order by verified_at desc
limit 1
"""

_SANCTIONS_SQL = """
select c.npi, c.first_name, c.last_name, c.credential, c.clinician_type, c.primary_specialty,
       s.source, s.action_type, s.action_date, s.description, s.reinstated_date,
       s.match_confidence, ev.source_key, ev.fetched_at
from sanctions s
join clinicians c on c.id = s.clinician_id and c.deleted_at is null
join affiliations a on a.clinician_id = c.id
     and a.practice_id = %(practice_id)s and a.end_date is null and a.deleted_at is null
left join evidence ev on ev.id = s.evidence_id
where s.deleted_at is null
order by s.action_date desc nulls last, c.last_name nulls last
"""

_SOURCES_SQL = """
select s.key, s.display_name, s.cadence, s.freshness_sla_days, s.enabled,
       s.is_primary_source, e.fetched_at, e.freshness_expires_at, e.parsed,
       r.started_at, r.status
from sources s
left join lateral (
    select fetched_at, freshness_expires_at, parsed
    from evidence
    where source_key = s.key and deleted_at is null
    order by fetched_at desc
    limit 1
) e on true
left join lateral (
    select started_at, status
    from source_runs
    where source_key = s.key
    order by started_at desc nulls last
    limit 1
) r on true
order by s.key
"""


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------


def format_zip(value: str | None) -> str:
    """Render a CMS ZIP, which is nine digits with no hyphen, readably."""
    raw = (value or "").strip()
    if len(raw) == 9 and raw.isdigit():
        return f"{raw[:5]}-{raw[5:]}"
    return raw


def format_phone(value: str | None) -> str:
    """Render a CMS telephone number, which is ten bare digits, readably."""
    raw = (value or "").strip()
    if len(raw) == 10 and raw.isdigit():
        return f"({raw[:3]}) {raw[3:6]}-{raw[6:]}"
    return raw


def _n(value: int | None) -> str:
    """Thousands-separated integer, or an em dash for None."""
    return f"{value:,}" if value is not None else "—"


def _person(first: str | None, last: str | None, credential: str | None) -> str:
    """Assemble a display name from the CMS name parts."""
    name = " ".join(part for part in ((first or "").title(), (last or "").title()) if part)
    name = name or "(name not published)"
    return f"{name}, {credential}" if credential else name


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """``1 clinician`` / ``4 clinicians``."""
    return f"{count:,} {singular if count == 1 else (plural or singular + 's')}"


def _days(count: int) -> str:
    """``1 day`` / ``31 days``."""
    return _plural(count, "day")


def _day_span(count: int) -> str:
    """``45-day``, for use as an adjective rather than a noun."""
    return f"{count:,}-day"


def _iso(value: date | datetime | None) -> str | None:
    """ISO 8601, or None."""
    return value.isoformat() if value is not None else None


def _clinician(row: Sequence[Any], offset: int = 0) -> ClinicianRef:
    """Build a :class:`ClinicianRef` from the six standard clinician columns."""
    npi, first, last, credential, clinician_type, specialty = row[offset : offset + 6]
    return ClinicianRef(
        npi=npi,
        name=_person(first, last, credential),
        credential=credential,
        clinician_type=clinician_type,
        primary_specialty=specialty,
    )


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def _load_sources(conn: psycopg.Connection, now: datetime) -> dict[str, SourceState]:
    """Read the source registry, its newest evidence and its newest run."""
    states: dict[str, SourceState] = {}
    for row in fetch_all(conn, _SOURCES_SQL):
        (
            key,
            display_name,
            cadence,
            sla_days,
            enabled,
            is_primary,
            fetched_at,
            expires_at,
            parsed,
            started_at,
            run_status,
        ) = row
        age_days = (now - fetched_at).days if fetched_at is not None else None
        states[key] = SourceState(
            key=key,
            display_name=display_name,
            cadence=cadence,
            freshness_sla_days=sla_days,
            enabled=bool(enabled),
            is_primary_source=bool(is_primary),
            fetched_at=fetched_at,
            expires_at=expires_at,
            stale=bool(expires_at is not None and expires_at < now),
            age_days=age_days,
            last_run_at=started_at,
            last_run_status=run_status,
            parsed=parsed if isinstance(parsed, dict) else {},
        )
    return states


def _cite(*sources: SourceState | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Turn source states into (keys, citations) for a :class:`Finding`."""
    present = [s for s in sources if s is not None]
    return tuple(s.key for s in present), tuple(s.citation() for s in present)


def _build_exclusion_screen(
    conn: psycopg.Connection,
    practice_id: Any,
    roster: Sequence[ClinicianRef],
    sources: Mapping[str, SourceState],
) -> ExclusionScreen:
    """Screen the roster against LEIE and SAM, and describe what was not screened."""
    hits: list[ExclusionRow] = []
    for row in fetch_all(conn, _SANCTIONS_SQL, {"practice_id": practice_id}):
        confidence = row[11]
        hits.append(
            ExclusionRow(
                clinician=_clinician(row),
                source=row[6],
                action_type=row[7],
                action_date=row[8],
                description=row[9],
                reinstated_date=row[10],
                match_confidence=float(confidence)
                if isinstance(confidence, Decimal)
                else confidence,
                evidence_source_key=row[12],
                evidence_fetched_at=row[13],
            )
        )

    leie = sources.get("oig_leie")
    sam = sources.get("sam_gov")
    parsed = leie.parsed if leie else {}
    total = parsed.get("rows_total")
    with_npi = parsed.get("rows_with_npi")
    unscreened = total - with_npi if isinstance(total, int) and isinstance(with_npi, int) else None

    return ExclusionScreen(
        roster_size=len(roster),
        leie_screened=bool(leie and leie.ingested),
        leie_records_total=total if isinstance(total, int) else None,
        leie_records_with_npi=with_npi if isinstance(with_npi, int) else None,
        leie_records_unscreened=unscreened,
        leie_name_dob_enabled=bool(parsed.get("name_dob_matching_enabled")),
        leie_source=leie,
        sam_screened=bool(sam and sam.ingested),
        sam_source=sam,
        hits=tuple(hits),
    )


def exclusion_caveat(screen: ExclusionScreen) -> str:
    """The sentence that keeps a clean screen from reading as a clearance.

    This wording is load-bearing. NPI coverage in the LEIE file is about 10%,
    so "no exclusions found" and "no exclusions" are separated by roughly
    75,000 records this system cannot match. The result always states the
    denominator it actually screened, and always ends by refusing the stronger
    claim.

    Args:
        screen: The screen to describe.

    Returns:
        A paragraph, safe to print verbatim in front of a prospect.
    """
    if not screen.leie_screened:
        return (
            f"The OIG LEIE exclusion screen was not run. No evidence row exists for the "
            f"oig_leie source, so none of the {_plural(screen.roster_size, 'clinician')} "
            f"on this roster has been screened against the List of Excluded Individuals "
            f"and Entities. This section reports the absence of a screen, not the absence "
            f"of an exclusion."
        )

    open_hits = screen.open_hits
    if open_hits:
        lead = (
            f"{_plural(len(open_hits), 'clinician')} on this roster matched an open OIG "
            f"exclusion by NPI. An excluded individual may not be paid by any federal "
            f"health care program, and a claim submitted for their services is an "
            f"overpayment and may carry civil monetary penalties."
        )
    else:
        lead = (
            f"No NPI-matched exclusions among the "
            f"{_plural(screen.roster_size, 'clinician')} on this roster."
        )

    matching = (
        "name-and-date-of-birth matching is enabled"
        if screen.leie_name_dob_enabled
        else "name-and-date-of-birth matching is not enabled in this system"
    )
    if screen.leie_records_unscreened is not None and screen.leie_records_total is not None:
        coverage = (
            f"{_n(screen.leie_records_unscreened)} of the {_n(screen.leie_records_total)} "
            f"records in the OIG LEIE file carry no NPI and were not screened, and "
            f"{matching}."
        )
    else:
        coverage = (
            f"The share of the OIG LEIE file that carries no NPI was not recorded by the "
            f"ingest run, so the number of unscreened records could not be quantified here; "
            f"{matching}."
        )

    sentences = [
        lead,
        coverage,
        "NPI matching is the only matching performed.",
    ]
    source = screen.leie_source
    if source is not None and source.stale and source.fetched_at is not None:
        sentences.append(
            f"The LEIE snapshot screened was fetched {source.fetched_at.date().isoformat()}, "
            f"{_days(source.age_days or 0)} ago, past this system's "
            f"{_day_span(source.freshness_sla_days)} freshness limit; exclusions published "
            f"since then are not represented."
        )
    sentences.append(
        "This result means that no clinician on this roster matched an excluded party by "
        "NPI. It does not mean that no clinician on this roster is excluded."
        if not open_hits
        else (
            f"{'That match was' if len(open_hits) == 1 else 'Those matches were'} made on "
            f"NPI. Nothing here rules out an exclusion among the rest of the roster: an NPI "
            f"match is the only kind this screen can make."
        )
    )
    return " ".join(sentences)


def sam_caveat(screen: ExclusionScreen) -> str:
    """State plainly whether SAM.gov was screened, and if not, why not."""
    sam = screen.sam_source
    if sam is None:
        return (
            "SAM.gov debarment screening was not performed: the sam_gov source is not "
            f"present in the source registry. {_plural(screen.roster_size, 'clinician')} "
            "on this roster is unscreened against SAM.gov."
            if screen.roster_size == 1
            else (
                "SAM.gov debarment screening was not performed: the sam_gov source is not "
                f"present in the source registry. All "
                f"{_plural(screen.roster_size, 'clinician')} on this roster are unscreened "
                "against SAM.gov."
            )
        )
    if screen.sam_screened:
        return (
            f"SAM.gov was screened against the snapshot fetched "
            f"{sam.fetched_at.date().isoformat() if sam.fetched_at else 'unknown'}. "
            "SAM.gov exclusion records are matched on name and organization, not on NPI; "
            "a SAM.gov result is therefore weaker evidence of identity than an NPI match."
        )
    status = "registered but disabled" if not sam.enabled else "registered and enabled"
    return (
        f"SAM.gov debarment screening was not performed. The sam_gov source is {status} "
        f"and has never produced an evidence row, so all "
        f"{_plural(screen.roster_size, 'clinician')} on this roster are unscreened against "
        "the federal exclusion list maintained outside HHS. A clinician can be debarred "
        "government-wide without appearing on the OIG list."
    )


def _build_enrollment(
    conn: psycopg.Connection,
    practice_id: Any,
    roster: Sequence[ClinicianRef],
    sources: Mapping[str, SourceState],
    as_of: date,
) -> EnrollmentReality:
    """Read Medicare revalidation position for the group and each clinician."""
    rows: list[RevalidationRow] = []
    enrolled_npis: set[str] = set()
    roster_npis = {c.npi for c in roster}
    for row in fetch_all(conn, _ENROLLMENTS_SQL, {"practice_id": practice_id}):
        clinician = _clinician(row)
        enrolled_npis.add(clinician.npi)
        due = row[7]
        days_overdue = (as_of - due).days if due is not None and due < as_of else None
        days_until = (due - as_of).days if due is not None and due >= as_of else None
        rows.append(
            RevalidationRow(
                clinician=clinician,
                status=row[6],
                revalidation_due=due,
                days_overdue=days_overdue,
                days_until_due=days_until,
                unbillable_days=(
                    max(0, days_overdue - RETROSPECTIVE_BILLING_DAYS)
                    if days_overdue is not None
                    else None
                ),
                on_roster=clinician.npi in roster_npis,
            )
        )

    group_row = fetch_all(conn, _GROUP_ENROLLMENT_SQL, {"practice_id": practice_id})
    group_due: date | None = None
    group_overdue: int | None = None
    group_known = bool(group_row)
    if group_row:
        group_due = group_row[0][1]
        if group_due is not None and group_due < as_of:
            group_overdue = (as_of - group_due).days
        group_note = (
            "Group due date is taken from the group-level Medicare enrollment row for this "
            "practice, derived from the CMS Revalidation Clinic Group Practice Reassignment "
            "file."
        )
    else:
        group_note = (
            "The group's own revalidation due date could not be determined. The CMS "
            "revalidation file publishes a Group Due Date alongside each individual "
            "reassignment, but this system's ingest derives only the per-clinician rows "
            "and stores no group-level Medicare enrollment for this practice. The group "
            "date is therefore unknown here -- not known to be clear."
        )

    unenrolled = tuple(c for c in roster if c.npi not in enrolled_npis)
    unaffiliated = tuple(r.clinician for r in rows if r.clinician.npi not in roster_npis)

    return EnrollmentReality(
        source=sources.get("cms_revalidation"),
        group_due_date=group_due,
        group_days_overdue=group_overdue,
        group_state_known=group_known,
        group_note=group_note,
        rows=tuple(rows),
        overdue=tuple(r for r in rows if r.days_overdue is not None),
        due_soon=tuple(
            r for r in rows if r.days_until_due is not None and r.days_until_due <= DUE_SOON_DAYS
        ),
        no_due_date=tuple(r for r in rows if r.revalidation_due is None),
        unenrolled=unenrolled,
        unaffiliated=unaffiliated,
    )


def _build_roster(
    conn: psycopg.Connection,
    practice_id: Any,
    roster: Sequence[ClinicianRef],
    sources: Mapping[str, SourceState],
) -> RosterComposition:
    """Count the roster by type, specialty, state and telehealth flag."""
    by_type: dict[str, int] = {}
    specialties: dict[str, int] = {}
    for clinician in roster:
        by_type[clinician.clinician_type] = by_type.get(clinician.clinician_type, 0) + 1
        if clinician.primary_specialty:
            key = clinician.primary_specialty
            specialties[key] = specialties.get(key, 0) + 1

    states = tuple(
        (state, count)
        for state, count in fetch_all(conn, _STATES_SQL, {"practice_id": practice_id})
    )

    # The DAC file carries a telehealth flag per clinician and the connector
    # stages it, but the clinicians table has no column for it in the migration
    # set this audit runs against. Probe rather than assume, so the section
    # turns itself on the day the column lands.
    telehealth_assessed = _has_column(conn, "clinicians", "telehealth")
    telehealth_count: int | None = None
    if telehealth_assessed:
        result = fetch_all(conn, _ROSTER_TELEHEALTH_SQL, {"practice_id": practice_id})
        telehealth_count = int(result[0][0] or 0) if result else 0
        telehealth_note = (
            "Telehealth participation is the CMS Doctors and Clinicians file's Telehlth "
            "flag, which CMS sets to Y or leaves blank; a blank is not an explicit N."
        )
    else:
        telehealth_note = (
            "The CMS Doctors and Clinicians file publishes a Telehlth flag per clinician "
            "and this system's ingest reads it, but does not retain it: there is no "
            "telehealth column on the clinicians table. The flag is in the source file, so "
            "this count becomes possible as soon as the column exists."
        )

    physicians = by_type.get("physician", 0)
    return RosterComposition(
        total=len(roster),
        by_type=dict(sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))),
        physicians=physicians,
        non_physicians=len(roster) - physicians,
        specialties=tuple(sorted(specialties.items(), key=lambda kv: (-kv[1], kv[0]))),
        distinct_specialties=len(specialties),
        states=states,
        telehealth_assessed=telehealth_assessed,
        telehealth_count=telehealth_count,
        telehealth_note=telehealth_note,
        source=sources.get("cms_dac"),
    )


def _build_directory(
    conn: psycopg.Connection,
    practice_id: Any,
    profile: PracticeProfile,
    sources: Mapping[str, SourceState],
) -> DirectoryAccuracy:
    """Report the directory record and everything that disagrees with it."""
    missing = tuple(
        label
        for label, value in (
            ("street address", profile.address_line1),
            ("city", profile.city),
            ("state", profile.state),
            ("ZIP code", profile.zip),
            ("telephone number", profile.phone),
            ("organizational NPI", profile.npi_org),
        )
        if not value
    )

    listings = tuple(
        OtherListing(
            clinician=_clinician(row),
            org_pac_id=row[6],
            legal_name=row[7],
            city=row[8],
            state=row[9],
        )
        for row in fetch_all(conn, _OTHER_LISTINGS_SQL, {"practice_id": practice_id})
    )

    dac = sources.get("cms_dac")
    stale = bool(dac and dac.stale)
    stale_note: str | None = None
    if dac and dac.ingested and stale:
        stale_note = (
            f"The directory snapshot these values come from was fetched "
            f"{dac.fetched_at.date().isoformat() if dac.fetched_at else 'unknown'}, "
            f"{_days(dac.age_days or 0)} ago, against a "
            f"{_day_span(dac.freshness_sla_days)} freshness limit. Any address, telephone "
            f"number or roster change CMS published since then is not reflected below."
        )

    return DirectoryAccuracy(
        profile=profile,
        directory_source=dac,
        missing_fields=missing,
        stale=stale,
        stale_note=stale_note,
        other_listings=listings,
        taxonomy_assessed=False,
        taxonomy_note=(
            "NPPES is the registry that holds taxonomy codes and the practice address of "
            "record, and the nppes source is registered in this system but not built: no "
            "evidence row exists for it. Taxonomy disagreement between NPPES and the CMS "
            "Doctors and Clinicians file is a routine directory finding, and this audit "
            "cannot make it."
        ),
        specialty_source_note=(
            "Specialty below is the CMS Doctors and Clinicians file's primary specialty, "
            "which is derived from the specialty code on the clinician's Medicare "
            "enrollment. It is not a board certification and it is not a taxonomy code."
        ),
    )


def _has_column(conn: psycopg.Connection, table: str, column: str) -> bool:
    """True when ``table.column`` exists on the current search_path."""
    if not table_exists(conn, table):
        return False
    rows = fetch_all(
        conn,
        """
        select 1 from information_schema.columns
        where table_name = %(table)s and column_name = %(column)s
        """,
        {"table": table, "column": column},
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def _findings(
    exclusions: ExclusionScreen,
    enrollment: EnrollmentReality,
    directory: DirectoryAccuracy,
    roster: RosterComposition,
    sources: Mapping[str, SourceState],
) -> tuple[Finding, ...]:
    """Assemble every finding the sections support, worst first.

    Nothing is invented and nothing is padded: a finding exists only where a
    row in the database supports it, and "not assessed" is itself a finding so
    that the gap is visible rather than silent.
    """
    found: list[Finding] = []

    def add(
        key: str,
        severity: Severity,
        title: str,
        detail: str,
        *cited: SourceState | None,
        quantity: int | None = None,
    ) -> None:
        source_keys, citations = _cite(*cited)
        found.append(
            Finding(
                key=key,
                severity=severity,
                title=title,
                detail=detail,
                source_keys=source_keys,
                citations=citations,
                quantity=quantity,
                rank=len(found),
            )
        )

    leie = exclusions.leie_source
    reval = enrollment.source
    dac = directory.directory_source

    # --- exclusions ------------------------------------------------------
    open_hits = exclusions.open_hits
    if open_hits:
        names = ", ".join(f"{h.clinician.name} (NPI {h.clinician.npi})" for h in open_hits)
        add(
            "exclusion_hit",
            Severity.CRITICAL,
            f"{_plural(len(open_hits), 'clinician')} on this roster is matched to an open "
            f"federal exclusion"
            if len(open_hits) == 1
            else f"{_plural(len(open_hits), 'clinician')} on this roster are matched to open "
            f"federal exclusions",
            f"{names}. Matched by NPI, which is an exact identity match. No federal health "
            f"care program may pay for items or services furnished by an excluded "
            f"individual, and no payment may be made to any entity that employs them in a "
            f"capacity for which payment is sought. Verify against the OIG exclusion "
            f"database directly before acting on this line.",
            leie,
            quantity=len(open_hits),
        )
    reinstated = [h for h in exclusions.hits if not h.open]
    if reinstated:
        add(
            "exclusion_reinstated",
            Severity.MEDIUM,
            f"{_plural(len(reinstated), 'clinician')} on this roster carries a closed OIG "
            f"exclusion record",
            "A reinstatement date is recorded, so the exclusion is not current. The history "
            "is still a payer credentialing disclosure and an OIG screening record.",
            leie,
            quantity=len(reinstated),
        )
    if exclusions.leie_screened and exclusions.leie_records_unscreened:
        add(
            "exclusion_coverage",
            Severity.NOT_ASSESSED,
            f"{_n(exclusions.leie_records_unscreened)} OIG LEIE records were not screened "
            f"against this roster",
            exclusion_caveat(exclusions),
            leie,
            quantity=exclusions.leie_records_unscreened,
        )
    if not exclusions.leie_screened:
        add(
            "exclusion_not_run",
            Severity.NOT_ASSESSED,
            "The OIG LEIE screen has not been run",
            exclusion_caveat(exclusions),
            leie,
            quantity=exclusions.roster_size,
        )
    if not exclusions.sam_screened:
        add(
            "sam_not_run",
            Severity.NOT_ASSESSED,
            f"{_plural(exclusions.roster_size, 'clinician')} unscreened against SAM.gov",
            sam_caveat(exclusions),
            exclusions.sam_source,
            quantity=exclusions.roster_size,
        )

    # --- enrollment ------------------------------------------------------
    if enrollment.group_days_overdue:
        add(
            "group_revalidation_overdue",
            Severity.CRITICAL,
            f"The group's Medicare revalidation is {_days(enrollment.group_days_overdue)} past due",
            f"CMS records a group revalidation due date of "
            f"{enrollment.group_due_date.isoformat() if enrollment.group_due_date else 'unknown'}. "
            f"A group that fails to revalidate can have its billing privileges deactivated, "
            f"which stops payment for every clinician reassigning to it, not only those with "
            f"individual lapses. {RETROSPECTIVE_BILLING_CITE} permits billing for services "
            f"furnished at most {RETROSPECTIVE_BILLING_DAYS} days before the effective date "
            f"of a reactivated enrollment, so a lapse longer than that window leaves services "
            f"with no billable path.",
            reval,
            quantity=enrollment.group_days_overdue,
        )
    elif not enrollment.group_state_known:
        add(
            "group_revalidation_unknown",
            Severity.NOT_ASSESSED,
            "The group's own Medicare revalidation date could not be determined",
            enrollment.group_note,
            reval,
        )

    if enrollment.overdue:
        off_roster = sum(1 for r in enrollment.overdue if not r.on_roster)
        if off_roster == 1:
            aside = (
                " One of them is not listed at this group in the CMS directory file but "
                "still reassigns billing rights to it."
            )
        elif off_roster:
            aside = (
                f" {off_roster:,} of them are not listed at this group in the CMS directory "
                f"file but still reassign billing rights to it."
            )
        else:
            aside = ""
        add(
            "individual_revalidation_overdue",
            Severity.HIGH,
            f"{_plural(len(enrollment.overdue), 'clinician')} billing under this group is "
            f"past their Medicare revalidation due date"
            if len(enrollment.overdue) == 1
            else f"{_plural(len(enrollment.overdue), 'clinician')} billing under this group "
            f"are past their Medicare revalidation due date",
            f"The longest lapse is {_days(enrollment.max_days_overdue)}. Where a lapse ends "
            f"in deactivation, {RETROSPECTIVE_BILLING_CITE} caps retrospective billing at "
            f"{RETROSPECTIVE_BILLING_DAYS} days before the reactivated effective date; "
            f"across these records {_n(enrollment.total_unbillable_days)} clinician-days "
            f"already sit outside that window. A past due date in the CMS file is not itself "
            f"a deactivation notice -- CMS deactivates after a revalidation request goes "
            f"unanswered -- so this quantifies exposure, not a realised loss.{aside}",
            reval,
            quantity=len(enrollment.overdue),
        )
    if enrollment.due_soon:
        add(
            "individual_revalidation_due_soon",
            Severity.MEDIUM,
            f"{_plural(len(enrollment.due_soon), 'clinician')} revalidate within "
            f"{DUE_SOON_DAYS} days",
            "CMS mails a revalidation request two to three months before the due date and "
            "accepts a submission no earlier than that. These are the ones with a date that "
            "has not yet passed.",
            reval,
            quantity=len(enrollment.due_soon),
        )
    if enrollment.no_due_date:
        add(
            "revalidation_no_due_date",
            Severity.LOW,
            f"{_plural(len(enrollment.no_due_date), 'clinician')} carries no CMS revalidation "
            f"due date",
            "CMS writes TBD in the due-date column when no revalidation date has been "
            "assigned. That is not the same as being clear: it means the date is not yet "
            "published and cannot be diarised.",
            reval,
            quantity=len(enrollment.no_due_date),
        )
    if enrollment.unenrolled:
        add(
            "roster_source_disagreement_missing_enrollment",
            Severity.MEDIUM,
            f"{_plural(len(enrollment.unenrolled), 'clinician')} appears in the CMS directory "
            f"for this group but in no Medicare reassignment record"
            if len(enrollment.unenrolled) == 1
            else f"{_plural(len(enrollment.unenrolled), 'clinician')} appear in the CMS "
            f"directory for this group but in no Medicare reassignment record",
            "The CMS Doctors and Clinicians file lists them at this group; the CMS "
            "Revalidation Clinic Group Practice Reassignment file carries no reassignment of "
            "their billing rights to it. Two federal files describing the same group "
            "disagree about who bills under it. Which one is wrong is not decidable from "
            "these sources, and this audit does not guess: it reports the disagreement.",
            dac,
            reval,
            quantity=len(enrollment.unenrolled),
        )
    if enrollment.unaffiliated:
        add(
            "roster_source_disagreement_missing_directory",
            Severity.MEDIUM,
            f"{_plural(len(enrollment.unaffiliated), 'clinician')} reassigns billing rights to "
            f"this group but is absent from the CMS directory for it"
            if len(enrollment.unaffiliated) == 1
            else f"{_plural(len(enrollment.unaffiliated), 'clinician')} reassign billing "
            f"rights to this group but are absent from the CMS directory for it",
            "The reverse of the disagreement above, and the more consequential direction: a "
            "clinician billing under a group that does not list them is the pattern a payer "
            "directory audit looks for.",
            dac,
            reval,
            quantity=len(enrollment.unaffiliated),
        )

    # --- directory -------------------------------------------------------
    if directory.stale and directory.stale_note:
        add(
            "directory_stale",
            Severity.MEDIUM,
            f"The directory snapshot is {_days(dac.age_days or 0) if dac else 'unknown'} old, "
            f"past its freshness limit",
            directory.stale_note,
            dac,
            quantity=dac.age_days if dac else None,
        )
    if directory.missing_fields:
        add(
            "directory_incomplete",
            Severity.LOW,
            f"CMS publishes no {', no '.join(directory.missing_fields)} for this practice",
            "A field CMS does not hold is a field a payer directory cannot be reconciled "
            "against, and it is the first thing a directory-accuracy review raises.",
            dac,
            quantity=len(directory.missing_fields),
        )
    if directory.other_listings:
        distinct = {listing.clinician.npi for listing in directory.other_listings}
        states = sorted({listing.state for listing in directory.other_listings if listing.state})
        add(
            "directory_multi_listing",
            Severity.LOW,
            f"{_plural(len(distinct), 'clinician')} on this roster is also listed by CMS at "
            f"another practice"
            if len(distinct) == 1
            else f"{_plural(len(distinct), 'clinician')} on this roster are also listed by CMS "
            f"at another practice",
            "CMS holds a separate practice address for them"
            + (f" in {', '.join(states)}" if states else "")
            + ". A second listing is normal for a clinician with more than one enrollment, "
            "and it is also how an address that was never updated after a departure "
            "persists in a federal directory. Each one is worth confirming.",
            dac,
            quantity=len(distinct),
        )
    add(
        "taxonomy_not_assessed",
        Severity.NOT_ASSESSED,
        "Provider taxonomy and the NPPES address of record were not checked",
        directory.taxonomy_note,
        sources.get("nppes"),
    )

    # --- roster ----------------------------------------------------------
    if not roster.telehealth_assessed:
        add(
            "telehealth_not_assessed",
            Severity.NOT_ASSESSED,
            "Telehealth-flagged clinicians were not counted",
            roster.telehealth_note,
            dac,
        )
    add(
        "licensure_not_assessed",
        Severity.NOT_ASSESSED,
        "State licence and controlled-substance registration status were not checked",
        "This audit reads federal files only. No state licensee file and no primary-source "
        "licence verification feed is ingested in this build, so nothing here speaks to "
        "whether a clinician's licence is active, encumbered or expired in any state.",
    )

    found.sort(key=lambda f: f.sort_key)
    return tuple(found)


def _limitations() -> tuple[str, ...]:
    """The standing caveats, printed whether or not anything was found."""
    limits = [
        "This audit reads federal bulk files only. It makes no request to any payer portal, "
        "any state board, or any system belonging to the practice.",
        "Federal bulk files are published on a lag and describe enrollment and directory "
        "status as of the publication date, not today.",
        "A CMS revalidation due date in the past is not a deactivation notice. It states "
        "that the date has passed.",
    ]
    return tuple(limits)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_practice(
    org_pac_id: str,
    *,
    conn: psycopg.Connection | None = None,
    settings: Settings | None = None,
    as_of: date | None = None,
) -> AuditResult:
    """Produce the free roster audit for one practice.

    Reads only what is already in the database. Nothing is fetched, nothing is
    written, and the practice is identified by its CMS group PAC ID alone.

    Args:
        org_pac_id: CMS group PAC ID, the universal join key.
        conn: An open connection to reuse; one is opened and closed when omitted.
        settings: Settings used when opening a connection.
        as_of: The date the audit is computed against. Defaults to today (UTC),
            and is an argument so the output is reproducible in a test.

    Returns:
        The completed :class:`AuditResult`.

    Raises:
        PracticeNotFound: If no practice carries ``org_pac_id``.
    """
    if conn is not None:
        return _audit(conn, org_pac_id, as_of)
    owned = connect(settings)
    try:
        return _audit(owned, org_pac_id, as_of)
    finally:
        owned.close()


def _audit(conn: psycopg.Connection, org_pac_id: str, as_of: date | None) -> AuditResult:
    """Run every section against an open connection."""
    generated_at = datetime.now(UTC)
    effective = as_of or generated_at.date()

    rows = fetch_all(conn, _PRACTICE_SQL, {"org_pac_id": org_pac_id})
    if not rows:
        raise PracticeNotFound(
            f"no practice with org_pac_id {org_pac_id!r}. The audit reads practices created "
            f"by the CMS Doctors and Clinicians ingest; if that PAC ID is real, the file has "
            f"not been loaded yet."
        )
    row = rows[0]
    practice_id = row[0]
    profile = PracticeProfile(
        org_pac_id=row[1],
        legal_name=row[3],
        dba_name=row[4],
        npi_org=row[2],
        address_line1=row[5],
        address_line2=row[6],
        city=row[7],
        state=row[8],
        zip=row[9],
        phone=row[10],
    )

    sources = _load_sources(conn, generated_at)
    roster_rows = fetch_all(conn, _ROSTER_SQL, {"practice_id": practice_id})
    roster = [_clinician(r, offset=1) for r in roster_rows]

    exclusions = _build_exclusion_screen(conn, practice_id, roster, sources)
    enrollment = _build_enrollment(conn, practice_id, roster, sources, effective)
    composition = _build_roster(conn, practice_id, roster, sources)
    directory = _build_directory(conn, practice_id, profile, sources)
    findings = _findings(exclusions, enrollment, directory, composition, sources)

    ordered = tuple(sources[k] for k in AUDIT_SOURCE_KEYS if k in sources)
    return AuditResult(
        org_pac_id=org_pac_id,
        generated_at=generated_at,
        as_of=effective,
        practice=profile,
        roster=composition,
        exclusions=exclusions,
        enrollment=enrollment,
        directory=directory,
        findings=findings,
        sources=ordered,
        limitations=_limitations(),
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Coerce the types the dataclasses hold into JSON-safe ones."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def result_to_dict(result: AuditResult) -> dict[str, Any]:
    """The audit as plain data, with the derived summary spelled out.

    Args:
        result: A completed audit.

    Returns:
        A dictionary whose every leaf is JSON-serializable after
        :func:`_jsonable`.
    """
    payload = asdict(result)
    payload["summary"] = {
        "worst_severity": result.worst_severity.value,
        "finding_count": len(result.findings),
        "counts_by_severity": result.counts_by_severity(),
        "roster_size": result.roster.total,
        "open_exclusion_hits": len(result.exclusions.open_hits),
        "revalidations_overdue": len(result.enrollment.overdue),
        "max_days_overdue": result.enrollment.max_days_overdue,
        "unbillable_clinician_days": result.enrollment.total_unbillable_days,
        "retrospective_billing_days": RETROSPECTIVE_BILLING_DAYS,
        "retrospective_billing_citation": RETROSPECTIVE_BILLING_CITE,
    }
    payload["exclusions"]["caveat"] = exclusion_caveat(result.exclusions)
    payload["exclusions"]["sam_caveat"] = sam_caveat(result.exclusions)
    return payload


def render_json(result: AuditResult) -> str:
    """Render the audit as indented JSON."""
    return json.dumps(result_to_dict(result), indent=2, default=_jsonable, sort_keys=False)


# ------------------------------------------------------------------ markdown

_SEVERITY_LABEL: dict[Severity, str] = {
    Severity.CRITICAL: "Critical",
    Severity.HIGH: "High",
    Severity.MEDIUM: "Medium",
    Severity.LOW: "Low",
    Severity.INFORMATIONAL: "Informational",
    Severity.NOT_ASSESSED: "Not assessed",
}


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """A GitHub-flavoured markdown table, or a dash when there are no rows."""
    body = list(rows)
    if not body:
        return "_No rows._\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in body]
    return "\n".join(out)


def _citation_text(finding: Finding) -> str:
    """The sources behind a finding, or an explicit statement that it has none."""
    if not finding.citations:
        return "not derived from an ingested source; stated as a limit of this build"
    return "; ".join(finding.citations)


def render_markdown(result: AuditResult) -> str:
    """Render the audit as a markdown findings document."""
    practice = result.practice
    out: list[str] = []
    w = out.append

    w(f"# Roster audit — {practice.legal_name}")
    w("")
    w(
        f"**CMS group PAC ID** {result.org_pac_id}  \n"
        f"**Prepared** {result.generated_at.date().isoformat()}  \n"
        f"**Dates assessed against** {result.as_of.isoformat()}  \n"
        f"**Clinicians on roster** {result.roster.total:,}"
    )
    w("")
    w(
        "This audit was produced from federal data already held by this system. "
        "No information was requested from the practice and no practice system was "
        "accessed. Every finding below names the file it came from and the date that "
        "file was fetched."
    )
    w("")

    # --- priority summary ------------------------------------------------
    w("## Findings, worst first")
    w("")
    counts = result.counts_by_severity()
    if counts:
        w(
            "  \n".join(
                f"**{_SEVERITY_LABEL[Severity(sev)]}** {count}"
                for sev, count in sorted(
                    counts.items(), key=lambda kv: SEVERITY_ORDER[Severity(kv[0])]
                )
            )
        )
        w("")
    w(
        _md_table(
            ["#", "Severity", "Finding", "Source, as fetched"],
            [
                [
                    str(i),
                    _SEVERITY_LABEL[f.severity],
                    f.title,
                    _citation_text(f),
                ]
                for i, f in enumerate(result.findings, start=1)
            ],
        )
    )
    for i, finding in enumerate(result.findings, start=1):
        w(f"**{i}. {finding.title}** — {_SEVERITY_LABEL[finding.severity]}")
        w("")
        w(finding.detail)
        w("")
        w(f"_Source: {_citation_text(finding)}_")
        w("")

    # --- 1. exclusions ---------------------------------------------------
    w("## 1. Exclusion and sanction screen")
    w("")
    w(exclusion_caveat(result.exclusions))
    w("")
    if result.exclusions.hits:
        w(
            _md_table(
                ["Clinician", "NPI", "Source", "Type", "Excluded", "Reinstated", "Match"],
                [
                    [
                        hit.clinician.name,
                        hit.clinician.npi,
                        hit.source.upper(),
                        hit.action_type or "—",
                        _iso(hit.action_date) or "—",
                        _iso(hit.reinstated_date) or "not reinstated",
                        "NPI, exact"
                        if (hit.match_confidence or 0) >= 1.0
                        else f"name/DOB, confidence {hit.match_confidence}",
                    ]
                    for hit in result.exclusions.hits
                ],
            )
        )
        w("")
    w(sam_caveat(result.exclusions))
    w("")

    # --- 2. enrollment ---------------------------------------------------
    w("## 2. Medicare enrollment reality")
    w("")
    reval = result.enrollment
    if reval.source is None or not reval.source.ingested:
        w(
            "The CMS revalidation file has not been ingested, so no Medicare enrollment "
            "position could be established for this group or for anyone on its roster."
        )
        w("")
    else:
        w("### The group")
        w("")
        if reval.group_due_date is not None:
            state = (
                f"**{_days(reval.group_days_overdue)} past due**"
                if reval.group_days_overdue
                else "not yet due"
            )
            w(
                f"Group revalidation due {reval.group_due_date.isoformat()} — {state}. "
                f"{reval.group_note}"
            )
        else:
            w(reval.group_note)
        w("")
        w("### Individual revalidations")
        w("")
        w(
            f"CMS records {_plural(len(reval.rows), 'Medicare reassignment')} of billing "
            f"rights to this group. Of those: {len(reval.overdue):,} past the revalidation "
            f"due date, {len(reval.due_soon):,} falling due within {DUE_SOON_DAYS} days, "
            f"{len(reval.no_due_date):,} with no date assigned by CMS."
        )
        w("")
        if reval.overdue:
            w(
                f"{RETROSPECTIVE_BILLING_CITE} allows a reactivated enrollment to bill for "
                f"services furnished at most {RETROSPECTIVE_BILLING_DAYS} days before its "
                f"effective date. The final column counts the days already outside that "
                f"window — services that, following a deactivation, no reactivation recovers."
            )
            w("")
            w(
                _md_table(
                    [
                        "Clinician",
                        "NPI",
                        "Specialty",
                        "On the CMS roster",
                        "Due",
                        "Days past due",
                        f"Days outside the {RETROSPECTIVE_BILLING_DAYS}-day window",
                    ],
                    [
                        [
                            row.clinician.name,
                            row.clinician.npi,
                            row.clinician.primary_specialty or "—",
                            "yes" if row.on_roster else "no",
                            _iso(row.revalidation_due) or "—",
                            f"{row.days_overdue:,}" if row.days_overdue else "0",
                            f"{row.unbillable_days:,}" if row.unbillable_days else "0",
                        ]
                        for row in sorted(reval.overdue, key=lambda r: -(r.days_overdue or 0))
                    ],
                )
            )
            w("")
            w(
                f"Total across these records: **{_n(reval.total_unbillable_days)} "
                f"clinician-days** already outside the {RETROSPECTIVE_BILLING_DAYS}-day "
                f"retrospective billing window. "
                f"A past due date is not a deactivation notice; CMS deactivates after a "
                f"revalidation request goes unanswered. This quantifies exposure, not a "
                f"realised loss."
            )
            w("")
        if reval.due_soon:
            w(f"**Falling due within {DUE_SOON_DAYS} days**")
            w("")
            w(
                _md_table(
                    ["Clinician", "NPI", "Due", "Days remaining"],
                    [
                        [
                            row.clinician.name,
                            row.clinician.npi,
                            _iso(row.revalidation_due) or "—",
                            f"{row.days_until_due:,}",
                        ]
                        for row in sorted(reval.due_soon, key=lambda r: r.days_until_due or 0)
                    ],
                )
            )
            w("")
        if reval.unenrolled or reval.unaffiliated:
            w("### Where the two federal files disagree")
            w("")
            w(
                "The CMS Doctors and Clinicians file and the CMS Revalidation Clinic Group "
                "Practice Reassignment file are both published by CMS and both describe who "
                "bills under this group. Where they disagree, that disagreement is the "
                "finding. This audit does not pick a winner."
            )
            w("")
            w(
                _md_table(
                    ["Clinician", "NPI", "In the directory file", "In the reassignment file"],
                    [[c.name, c.npi, "yes", "no"] for c in reval.unenrolled]
                    + [[c.name, c.npi, "no", "yes"] for c in reval.unaffiliated],
                )
            )
            w("")

    # --- 3. directory ----------------------------------------------------
    w("## 3. Directory accuracy")
    w("")
    directory = result.directory
    if directory.stale_note:
        w(directory.stale_note)
        w("")
    w("### What CMS publishes for this practice")
    w("")
    w(
        _md_table(
            ["Field", "As CMS holds it"],
            [
                ["Legal name", practice.legal_name],
                ["Doing business as", practice.dba_name or "not published"],
                ["Group PAC ID", practice.org_pac_id],
                ["Organizational NPI", practice.npi_org or "not published"],
                ["Address", " / ".join(practice.address_lines()) or "not published"],
                ["Telephone", format_phone(practice.phone) or "not published"],
            ],
        )
    )
    w("")
    if directory.missing_fields:
        w(
            f"CMS publishes no {', no '.join(directory.missing_fields)} for this practice. "
            f"A field CMS does not hold cannot be reconciled against a payer directory."
        )
        w("")
    w(directory.specialty_source_note)
    w("")
    if directory.other_listings:
        w("### Clinicians CMS also lists elsewhere")
        w("")
        w(
            "Each row is a second practice address CMS holds for someone on this roster. A "
            "second listing is ordinary for a clinician with more than one enrollment, and "
            "it is also how an address that was never updated after a departure survives in "
            "a federal directory."
        )
        w("")
        w(
            _md_table(
                ["Clinician", "NPI", "Also listed at", "Group PAC ID", "City", "State"],
                [
                    [
                        listing.clinician.name,
                        listing.clinician.npi,
                        listing.legal_name,
                        listing.org_pac_id or "—",
                        listing.city or "—",
                        listing.state or "—",
                    ]
                    for listing in directory.other_listings
                ],
            )
        )
        w("")
    w(f"**Taxonomy.** {directory.taxonomy_note}")
    w("")

    # --- 4. roster -------------------------------------------------------
    w("## 4. Roster composition")
    w("")
    roster = result.roster
    w(
        _md_table(
            ["Measure", "Count"],
            [
                ["Clinicians on roster", f"{roster.total:,}"],
                ["Physicians (MD/DO)", f"{roster.physicians:,}"],
                ["Non-physician clinicians", f"{roster.non_physicians:,}"],
                ["Distinct primary specialties", f"{roster.distinct_specialties:,}"],
                [
                    "Telehealth-flagged",
                    f"{roster.telehealth_count:,}"
                    if roster.telehealth_assessed
                    else "not assessed",
                ],
                ["States CMS lists this roster in", f"{len(roster.states):,}"],
            ],
        )
    )
    w("")
    if roster.by_type:
        w("**Clinician types**")
        w("")
        w(
            _md_table(
                ["Clinician type", "Count"],
                [[k, f"{v:,}"] for k, v in roster.by_type.items()],
            )
        )
        w("")
    if roster.specialties:
        w("**Specialty mix**")
        w("")
        w(
            _md_table(
                ["Primary specialty", "Clinicians"],
                [[k, f"{v:,}"] for k, v in roster.specialties],
            )
        )
        w("")
    if roster.states:
        w("**States**")
        w("")
        w(
            _md_table(
                ["State", "Clinicians on this roster listed there"],
                [[state, f"{count:,}"] for state, count in roster.states],
            )
        )
        w("")
    if not roster.telehealth_assessed:
        w(roster.telehealth_note)
        w("")

    # --- 5. not assessed -------------------------------------------------
    w("## 5. What this audit did not assess")
    w("")
    w("Listed rather than omitted, because an omitted section reads as a clean result.")
    w("")
    for finding in result.findings:
        if finding.severity is Severity.NOT_ASSESSED:
            w(f"- **{finding.title}.** {finding.detail}")
    for limitation in result.limitations:
        w(f"- {limitation}")
    w("")

    # --- methodology -----------------------------------------------------
    w("## Methodology and sources")
    w("")
    w(
        "Every number above comes from a federal bulk file already loaded into this "
        "system. Nothing was fetched to produce this document and nothing was inferred "
        "from a source not named here."
    )
    w("")
    w(
        _md_table(
            ["Source", "Publisher's cadence", "Snapshot fetched", "Age", "Within freshness limit"],
            [
                [
                    source.display_name or source.key,
                    source.cadence or "—",
                    source.fetched_at.date().isoformat() if source.fetched_at else "never ingested",
                    _days(source.age_days) if source.age_days is not None else "—",
                    ("not ingested" if not source.ingested else ("no" if source.stale else "yes"))
                    + f" ({_day_span(source.freshness_sla_days)} limit)",
                ]
                for source in result.sources
            ],
        )
    )
    w("")
    w(
        "Refresh cadence in this system: the CMS Doctors and Clinicians file, the CMS "
        "revalidation file and the OIG LEIE file are published monthly and re-ingested "
        "monthly. SAM.gov publishes daily. Each source carries a freshness limit, shown "
        "above; past it, this system treats its assertions as stale rather than current."
    )
    w("")
    w(
        f"Roster membership is the set of clinicians with an open affiliation to group PAC "
        f"ID {result.org_pac_id} in the CMS Doctors and Clinicians file, deduplicated on "
        f"(NPI, group PAC ID) so a clinician working several locations of the same group "
        f"counts once. Revalidation dates are the individual and group due dates published "
        f"in the CMS Revalidation Clinic Group Practice Reassignment file. Exclusions are "
        f"NPI matches against the OIG List of Excluded Individuals and Entities."
    )
    w("")
    w(
        "This document is a screen against federal files, not a primary-source "
        "verification and not legal advice. Before acting on any line, confirm it against "
        "the publisher: PECOS for enrollment, the OIG exclusion database for an exclusion."
    )
    w("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

#: Typography and palette are the operating pack's: cream ground, Bitter for
#: headings, Public Sans for body, an ochre accent. Light only and no dark-mode
#: media query, because the artifact's destination is a printed PDF and a page
#: that flips to dark under a reviewer's OS setting prints as a black rectangle.
#: The web fonts are linked, and every family carries a local fallback so the
#: page sets correctly when it is rendered with no network.
_HTML_CSS = """
:root{
  color-scheme: light;
  --ground:#F5F5F1; --surface:#FFFFFF; --surface-2:#EBEBE5;
  --ink:#1A1D1F; --muted:#585E64; --faint:#8A9096;
  --line:#DEDED7; --line-strong:#C4C5BC;
  --accent:#96652B; --accent-soft:#F1E7D7;
  --structure:#3B5B6A; --structure-soft:#DFE9ED;
  --easy:#4A6B3D; --easy-soft:#E2EBDC;
  --alert:#8C3A2B; --alert-soft:#F3E3DF;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{background:var(--ground);color:var(--ink);margin:0;
  font-family:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:15px;line-height:1.6}
.wrap{max-width:1000px;margin:0 auto;padding:34px 24px 72px}
h1,h2,h3,h4{font-family:Bitter,Georgia,"Times New Roman",serif;margin:0;letter-spacing:-.012em;
  text-wrap:balance}
h1{font-size:34px;font-weight:700;line-height:1.08;margin-top:8px}
h2{font-size:22px;font-weight:600}
h3{font-size:16.5px;font-weight:600;margin:26px 0 8px}
h4{font-size:14.5px;font-weight:600}
p{max-width:84ch;color:var(--muted);margin:0 0 12px}
p b,li b,td b{color:var(--ink);font-weight:600}
ul{max-width:84ch;color:var(--muted);padding-left:19px;margin:0 0 12px}
li{margin-bottom:7px}
.eyebrow{font-family:"Roboto Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--faint)}
header{border-bottom:2px solid var(--ink);padding-bottom:20px}
.sub{font-size:16px;line-height:1.5;color:var(--muted);max-width:70ch;margin-top:12px}
.metabar{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:10px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--faint);
  border:1px solid var(--line);background:var(--surface);border-radius:2px;
  padding:9px 13px;margin:20px 0 0;display:flex;flex-wrap:wrap;gap:6px 18px}
.metabar b{color:var(--accent);font-weight:500}
section{margin-top:44px;break-inside:auto}
.sechead{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid var(--line-strong);
  padding-bottom:9px;margin-bottom:16px}
.sechead .n{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:11px;
  color:var(--accent);letter-spacing:.1em}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin:20px 0}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:2px;padding:14px 16px;
  break-inside:avoid}
.kpi .v{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:24px;font-weight:600;
  color:var(--accent);letter-spacing:-.025em;line-height:1.1}
.kpi.crit .v{color:var(--alert)}
.kpi.clear .v{color:var(--easy)}
.kpi .k{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.4}
.tablewrap{margin:16px 0;border:1px solid var(--line);border-radius:2px;background:var(--surface);
  overflow-x:auto}
table{border-collapse:collapse;width:100%}
th{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:9.5px;letter-spacing:.11em;
  text-transform:uppercase;color:var(--faint);text-align:left;font-weight:500;padding:10px 12px;
  border-bottom:1px solid var(--line-strong)}
td{padding:9px 12px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top;
  line-height:1.45;color:var(--muted)}
tr{break-inside:avoid}
tr:last-child td{border-bottom:none}
td.n{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;
  white-space:nowrap;color:var(--ink)}
td strong{font-weight:600;color:var(--ink)}
.sev{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:9.5px;letter-spacing:.1em;
  text-transform:uppercase;padding:3px 7px;border-radius:2px;white-space:nowrap;
  border:1px solid var(--line-strong);color:var(--muted);background:var(--surface-2)}
.sev-critical{background:var(--alert-soft);border-color:var(--alert);color:var(--alert)}
.sev-high{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.sev-medium{background:var(--structure-soft);border-color:var(--structure);color:var(--structure)}
.sev-low,.sev-informational{background:var(--surface-2)}
.sev-not_assessed{background:var(--surface);border-style:dashed}
.finding{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--line-strong);
  border-radius:2px;padding:15px 19px;margin:12px 0;break-inside:avoid}
.finding.critical{border-left-color:var(--alert)}
.finding.high{border-left-color:var(--accent)}
.finding.medium{border-left-color:var(--structure)}
.finding.not_assessed{border-left-style:dashed}
.finding h4{margin:0 0 6px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.finding p{margin:0 0 8px;font-size:13.5px;line-height:1.55}
.cite{font-family:"Roboto Mono",ui-monospace,Menlo,monospace;font-size:10px;color:var(--faint);
  letter-spacing:.04em;margin:0}
.box{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--structure);
  border-radius:2px;padding:16px 20px;margin:16px 0;break-inside:avoid}
.box.key{border-left-color:var(--accent);background:var(--accent-soft)}
.box.alert{border-left-color:var(--alert);background:var(--alert-soft)}
.box p{margin:0 0 7px;font-size:13.5px;line-height:1.55;max-width:82ch}
.box p:last-child{margin-bottom:0}
.foot{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;
  color:var(--faint);line-height:1.6;max-width:84ch}
@page{size:Letter;margin:14mm}
@media print{
  body{background:#fff;font-size:10.5pt}
  .wrap{max-width:none;padding:0}
  section{break-before:auto}
  h2{break-after:avoid}
  .tablewrap{overflow:visible}
}
"""


def _e(value: Any) -> str:
    """HTML-escape a value, rendering None as an em dash."""
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def _html_table(
    headers: Sequence[str], rows: Iterable[Sequence[str]], numeric: Sequence[int] = ()
) -> str:
    """Render a table, already escaped, inside the pack's table wrapper.

    Args:
        headers: Column headings.
        rows: Pre-escaped cell HTML, row by row.
        numeric: Indices of columns to set in the monospaced tabular style.

    Returns:
        HTML for the table, or a short paragraph when there are no rows.
    """
    body = list(rows)
    if not body:
        return '<p class="cite">No rows.</p>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    out = [f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>']
    for row in body:
        cells = "".join(
            f'<td class="n">{cell}</td>' if i in set(numeric) else f"<td>{cell}</td>"
            for i, cell in enumerate(row)
        )
        out.append(f"<tr>{cells}</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _p(text: str) -> str:
    """One escaped paragraph."""
    return f"<p>{_e(text)}</p>"


def render_html(result: AuditResult) -> str:
    """Render the audit as a self-contained HTML page.

    The page carries its own stylesheet, prints to Letter without further
    styling, and contains no script. It is the artifact a prospect receives.

    Args:
        result: A completed audit.

    Returns:
        A complete HTML document.
    """
    practice = result.practice
    out: list[str] = []
    w = out.append

    title = f"Roster audit — {practice.legal_name}"
    w("<!doctype html>")
    w('<html lang="en"><head><meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width,initial-scale=1">')
    w(f"<title>{_e(title)}</title>")
    w(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        "family=Bitter:wght@600;700&family=Public+Sans:wght@400;500;600&"
        'family=Roboto+Mono:wght@400;500&display=swap">'
    )
    w(f"<style>{_HTML_CSS}</style>")
    w('</head><body><div class="wrap">')

    # --- header ----------------------------------------------------------
    w("<header>")
    w('<div class="eyebrow">Free roster audit &middot; federal sources only</div>')
    w(f"<h1>{_e(practice.legal_name)}</h1>")
    w(
        '<p class="sub">Produced from federal data already held by this system. Nothing was '
        "requested from the practice and no practice system was accessed. Every finding "
        "below names the file it came from and the date that file was fetched.</p>"
    )
    w("</header>")
    w(
        '<div class="metabar">'
        f"<span>Group PAC ID <b>{_e(result.org_pac_id)}</b></span>"
        f"<span>Prepared <b>{_e(result.generated_at.date().isoformat())}</b></span>"
        f"<span>Assessed against <b>{_e(result.as_of.isoformat())}</b></span>"
        f"<span>Roster <b>{result.roster.total:,}</b></span>"
        f"<span>Findings <b>{len(result.findings):,}</b></span>"
        "</div>"
    )

    # --- summary ---------------------------------------------------------
    exclusions = result.exclusions
    enrollment = result.enrollment
    open_hits = len(exclusions.open_hits)
    w('<section id="summary"><div class="sechead"><span class="n">00</span>')
    w("<h2>Findings, worst first</h2></div>")
    w('<div class="kpis">')
    w(
        f'<div class="kpi {"crit" if open_hits else "clear"}"><div class="v">{open_hits:,}</div>'
        '<div class="k">clinicians matched to an open federal exclusion, by NPI</div></div>'
    )
    w(
        f'<div class="kpi {"crit" if enrollment.overdue else ""}">'
        f'<div class="v">{len(enrollment.overdue):,}</div>'
        '<div class="k">clinicians past their Medicare revalidation due date</div></div>'
    )
    w(
        f'<div class="kpi"><div class="v">{enrollment.max_days_overdue:,}</div>'
        '<div class="k">days, longest revalidation lapse on the roster</div></div>'
    )
    w(
        f'<div class="kpi"><div class="v">{enrollment.total_unbillable_days:,}</div>'
        f'<div class="k">clinician-days already outside the '
        f"{RETROSPECTIVE_BILLING_DAYS}-day retrospective billing window</div></div>"
    )
    w(
        f'<div class="kpi"><div class="v">{_n(exclusions.leie_records_unscreened)}</div>'
        '<div class="k">OIG LEIE records that carry no NPI and were not screened</div></div>'
    )
    w("</div>")
    w(
        _html_table(
            ["#", "Severity", "Finding", "Source, as fetched"],
            [
                [
                    str(i),
                    f'<span class="sev sev-{f.severity.value}">'
                    f"{_e(_SEVERITY_LABEL[f.severity])}</span>",
                    f"<strong>{_e(f.title)}</strong>",
                    _e(_citation_text(f)),
                ]
                for i, f in enumerate(result.findings, start=1)
            ],
            numeric=(0,),
        )
    )
    for i, finding in enumerate(result.findings, start=1):
        w(f'<div class="finding {finding.severity.value}">')
        w(
            f"<h4><span>{i}. {_e(finding.title)}</span>"
            f'<span class="sev sev-{finding.severity.value}">'
            f"{_e(_SEVERITY_LABEL[finding.severity])}</span></h4>"
        )
        w(_p(finding.detail))
        w(f'<p class="cite">Source: {_e(_citation_text(finding))}</p>')
        w("</div>")
    w("</section>")

    # --- 1 exclusions ----------------------------------------------------
    w('<section id="exclusions"><div class="sechead"><span class="n">01</span>')
    w("<h2>Exclusion and sanction screen</h2></div>")
    w(
        f'<div class="box {"alert" if open_hits else "key"}">{_p(exclusion_caveat(exclusions))}</div>'
    )
    if exclusions.hits:
        w(
            _html_table(
                ["Clinician", "NPI", "List", "Type", "Excluded", "Reinstated", "Match"],
                [
                    [
                        f"<strong>{_e(hit.clinician.name)}</strong>",
                        _e(hit.clinician.npi),
                        _e(hit.source.upper()),
                        _e(hit.action_type),
                        _e(_iso(hit.action_date)),
                        _e(_iso(hit.reinstated_date) or "not reinstated"),
                        _e(
                            "NPI, exact"
                            if (hit.match_confidence or 0) >= 1.0
                            else f"name/DOB, confidence {hit.match_confidence}"
                        ),
                    ]
                    for hit in exclusions.hits
                ],
                numeric=(1, 4, 5),
            )
        )
    w(f'<div class="box">{_p(sam_caveat(exclusions))}</div>')
    w("</section>")

    # --- 2 enrollment ----------------------------------------------------
    w('<section id="enrollment"><div class="sechead"><span class="n">02</span>')
    w("<h2>Medicare enrollment reality</h2></div>")
    if enrollment.source is None or not enrollment.source.ingested:
        w(
            _p(
                "The CMS revalidation file has not been ingested, so no Medicare enrollment "
                "position could be established for this group or for anyone on its roster."
            )
        )
    else:
        w("<h3>The group</h3>")
        if enrollment.group_due_date is not None:
            state = (
                f"{_days(enrollment.group_days_overdue)} past due"
                if enrollment.group_days_overdue
                else "not yet due"
            )
            w(
                f'<div class="box {"alert" if enrollment.group_days_overdue else ""}">'
                f"<p><b>Group revalidation due "
                f"{_e(enrollment.group_due_date.isoformat())} &mdash; {_e(state)}.</b></p>"
                f"{_p(enrollment.group_note)}</div>"
            )
        else:
            w(f'<div class="box">{_p(enrollment.group_note)}</div>')
        w("<h3>Individual revalidations</h3>")
        w(
            _p(
                f"CMS records {_plural(len(enrollment.rows), 'Medicare reassignment')} of "
                f"billing rights to this group. Of those: {len(enrollment.overdue):,} past "
                f"the revalidation due date, {len(enrollment.due_soon):,} falling due within "
                f"{DUE_SOON_DAYS} days, {len(enrollment.no_due_date):,} with no date "
                f"assigned by CMS."
            )
        )
        if enrollment.overdue:
            w(
                _p(
                    f"{RETROSPECTIVE_BILLING_CITE} allows a reactivated enrollment to bill "
                    f"for services furnished at most {RETROSPECTIVE_BILLING_DAYS} days "
                    f"before its effective date. The final column counts the days already "
                    f"outside that window."
                )
            )
            w(
                _html_table(
                    [
                        "Clinician",
                        "NPI",
                        "Specialty",
                        "On the CMS roster",
                        "Due",
                        "Days past due",
                        f"Days outside the {RETROSPECTIVE_BILLING_DAYS}-day window",
                    ],
                    [
                        [
                            f"<strong>{_e(row.clinician.name)}</strong>",
                            _e(row.clinician.npi),
                            _e(row.clinician.primary_specialty),
                            "yes" if row.on_roster else "<b>no</b>",
                            _e(_iso(row.revalidation_due)),
                            f"{row.days_overdue:,}" if row.days_overdue else "0",
                            f"{row.unbillable_days:,}" if row.unbillable_days else "0",
                        ]
                        for row in sorted(enrollment.overdue, key=lambda r: -(r.days_overdue or 0))
                    ],
                    numeric=(1, 4, 5, 6),
                )
            )
            w(
                f'<div class="box key"><p>Across these records, '
                f"<b>{_n(enrollment.total_unbillable_days)} "
                f"clinician-days</b> already sit outside the "
                f"{RETROSPECTIVE_BILLING_DAYS}-day retrospective billing window.</p>"
                + _p(
                    "A past due date is not a deactivation notice. CMS deactivates billing "
                    "privileges after a revalidation request goes unanswered, and the date "
                    "in this file states only that the date has passed. This quantifies "
                    "exposure, not a realised loss."
                )
                + "</div>"
            )
        if enrollment.due_soon:
            w(f"<h3>Falling due within {DUE_SOON_DAYS} days</h3>")
            w(
                _html_table(
                    ["Clinician", "NPI", "Due", "Days remaining"],
                    [
                        [
                            f"<strong>{_e(row.clinician.name)}</strong>",
                            _e(row.clinician.npi),
                            _e(_iso(row.revalidation_due)),
                            f"{row.days_until_due:,}",
                        ]
                        for row in sorted(enrollment.due_soon, key=lambda r: r.days_until_due or 0)
                    ],
                    numeric=(1, 2, 3),
                )
            )
        if enrollment.unenrolled or enrollment.unaffiliated:
            w("<h3>Where the two federal files disagree</h3>")
            w(
                _p(
                    "The CMS Doctors and Clinicians file and the CMS Revalidation Clinic "
                    "Group Practice Reassignment file are both published by CMS and both "
                    "describe who bills under this group. Where they disagree, the "
                    "disagreement is the finding. This audit does not pick a winner."
                )
            )
            w(
                _html_table(
                    ["Clinician", "NPI", "In the directory file", "In the reassignment file"],
                    [
                        [f"<strong>{_e(c.name)}</strong>", _e(c.npi), "yes", "<b>no</b>"]
                        for c in enrollment.unenrolled
                    ]
                    + [
                        [f"<strong>{_e(c.name)}</strong>", _e(c.npi), "<b>no</b>", "yes"]
                        for c in enrollment.unaffiliated
                    ],
                    numeric=(1,),
                )
            )
    w("</section>")

    # --- 3 directory -----------------------------------------------------
    directory = result.directory
    w('<section id="directory"><div class="sechead"><span class="n">03</span>')
    w("<h2>Directory accuracy</h2></div>")
    if directory.stale_note:
        w(f'<div class="box">{_p(directory.stale_note)}</div>')
    w("<h3>What CMS publishes for this practice</h3>")
    w(
        _html_table(
            ["Field", "As CMS holds it"],
            [
                ["Legal name", f"<strong>{_e(practice.legal_name)}</strong>"],
                ["Doing business as", _e(practice.dba_name or "not published")],
                ["Group PAC ID", _e(practice.org_pac_id)],
                ["Organizational NPI", _e(practice.npi_org or "not published")],
                [
                    "Address",
                    "<br>".join(_e(line) for line in practice.address_lines())
                    or _e("not published"),
                ],
                ["Telephone", _e(format_phone(practice.phone) or "not published")],
            ],
        )
    )
    if directory.missing_fields:
        w(
            _p(
                f"CMS publishes no {', no '.join(directory.missing_fields)} for this "
                f"practice. A field CMS does not hold cannot be reconciled against a payer "
                f"directory."
            )
        )
    w(_p(directory.specialty_source_note))
    if directory.other_listings:
        w("<h3>Clinicians CMS also lists elsewhere</h3>")
        w(
            _p(
                "Each row is a second practice address CMS holds for someone on this "
                "roster. A second listing is ordinary for a clinician with more than one "
                "enrollment, and it is also how an address never updated after a departure "
                "survives in a federal directory."
            )
        )
        w(
            _html_table(
                ["Clinician", "NPI", "Also listed at", "Group PAC ID", "City", "State"],
                [
                    [
                        f"<strong>{_e(listing.clinician.name)}</strong>",
                        _e(listing.clinician.npi),
                        _e(listing.legal_name),
                        _e(listing.org_pac_id),
                        _e(listing.city),
                        _e(listing.state),
                    ]
                    for listing in directory.other_listings
                ],
                numeric=(1, 3),
            )
        )
    w(f'<div class="box">{_p(directory.taxonomy_note)}</div>')
    w("</section>")

    # --- 4 roster --------------------------------------------------------
    roster = result.roster
    w('<section id="roster"><div class="sechead"><span class="n">04</span>')
    w("<h2>Roster composition</h2></div>")
    w(
        _html_table(
            ["Measure", "Count"],
            [
                ["Clinicians on roster", f"{roster.total:,}"],
                ["Physicians (MD/DO)", f"{roster.physicians:,}"],
                ["Non-physician clinicians", f"{roster.non_physicians:,}"],
                ["Distinct primary specialties", f"{roster.distinct_specialties:,}"],
                [
                    "Telehealth-flagged",
                    f"{roster.telehealth_count:,}"
                    if roster.telehealth_assessed
                    else "<em>not assessed</em>",
                ],
                ["States CMS lists this roster in", f"{len(roster.states):,}"],
            ],
            numeric=(1,),
        )
    )
    if roster.by_type:
        w("<h3>Clinician types</h3>")
        w(
            _html_table(
                ["Clinician type", "Count"],
                [[_e(k), f"{v:,}"] for k, v in roster.by_type.items()],
                numeric=(1,),
            )
        )
    if roster.specialties:
        w("<h3>Specialty mix</h3>")
        w(
            _html_table(
                ["Primary specialty", "Clinicians"],
                [[_e(k), f"{v:,}"] for k, v in roster.specialties],
                numeric=(1,),
            )
        )
    if roster.states:
        w("<h3>States</h3>")
        w(
            _html_table(
                ["State", "Clinicians on this roster listed there"],
                [[_e(state), f"{count:,}"] for state, count in roster.states],
                numeric=(1,),
            )
        )
    if not roster.telehealth_assessed:
        w(f'<div class="box">{_p(roster.telehealth_note)}</div>')
    w("</section>")

    # --- 5 not assessed --------------------------------------------------
    w('<section id="not-assessed"><div class="sechead"><span class="n">05</span>')
    w("<h2>What this audit did not assess</h2></div>")
    w(_p("Listed rather than omitted, because an omitted section reads as a clean result."))
    w("<ul>")
    for finding in result.findings:
        if finding.severity is Severity.NOT_ASSESSED:
            w(f"<li><b>{_e(finding.title)}.</b> {_e(finding.detail)}</li>")
    for limitation in result.limitations:
        w(f"<li>{_e(limitation)}</li>")
    w("</ul>")
    w("</section>")

    # --- methodology -----------------------------------------------------
    w('<section id="methodology"><div class="sechead"><span class="n">06</span>')
    w("<h2>Methodology and sources</h2></div>")
    w(
        _p(
            "Every number above comes from a federal bulk file already loaded into this "
            "system. Nothing was fetched to produce this document and nothing was inferred "
            "from a source not named here."
        )
    )
    w(
        _html_table(
            ["Source", "Cadence", "Snapshot fetched", "Age", "Within freshness limit"],
            [
                [
                    _e(source.display_name or source.key),
                    _e(source.cadence),
                    _e(
                        source.fetched_at.date().isoformat()
                        if source.fetched_at
                        else "never ingested"
                    ),
                    _e(_days(source.age_days) if source.age_days is not None else None),
                    _e(
                        (
                            "not ingested"
                            if not source.ingested
                            else ("no" if source.stale else "yes")
                        )
                        + f" ({_day_span(source.freshness_sla_days)} limit)"
                    ),
                ]
                for source in result.sources
            ],
            numeric=(2, 3),
        )
    )
    w(
        _p(
            "Refresh cadence in this system: the CMS Doctors and Clinicians file, the CMS "
            "revalidation file and the OIG LEIE file are published monthly and re-ingested "
            "monthly. SAM.gov publishes daily. Each source carries a freshness limit, shown "
            "above; past it, this system treats its assertions as stale rather than current."
        )
    )
    w(
        _p(
            f"Roster membership is the set of clinicians with an open affiliation to group "
            f"PAC ID {result.org_pac_id} in the CMS Doctors and Clinicians file, "
            f"deduplicated on (NPI, group PAC ID) so a clinician working several locations "
            f"of the same group counts once. Revalidation dates are the individual and "
            f"group due dates published in the CMS Revalidation Clinic Group Practice "
            f"Reassignment file. Exclusions are NPI matches against the OIG List of "
            f"Excluded Individuals and Entities."
        )
    )
    w("</section>")

    w(
        '<div class="foot">This document is a screen against federal files. It is not a '
        "primary-source verification, not a credentialing decision and not legal advice. "
        "Before acting on any line, confirm it against the publisher: PECOS for enrollment, "
        "the OIG exclusion database for an exclusion. "
        f"Generated {_e(result.generated_at.isoformat(timespec='seconds'))}.</div>"
    )
    w("</div></body></html>")
    return "\n".join(out)
