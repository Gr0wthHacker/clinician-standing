"""Turn stored records into a standing response.

Pure functions over the records in :mod:`.store`; no I/O. The wording of each
``note`` is part of the contract. A screen that found nothing states how much it
could not see, because "no match" against roughly a tenth of the OIG file is a
much weaker statement than it sounds, and a caller acting on the weaker
statement as if it were the stronger one is the failure this module exists to
prevent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from .models import (
    CheckRequest,
    ClinicianStanding,
    ExclusionMatch,
    ExclusionScreen,
    ExclusionStatus,
    Identity,
    LicenseCoverage,
    LicenseRecordOut,
    LicenseScreen,
    LookupResult,
    PossibleExclusionMatch,
    SourceRole,
    SourcesBlock,
    SourcesResponse,
    SourceStatus,
    StandingResponse,
)
from .store import ClinicianRecord, SourceRecord, StandingStore

__all__ = [
    "MAX_CANDIDATES",
    "SCOPE",
    "build_sources_block",
    "check",
    "classify_source",
    "sources_response",
]

#: Name lookups return at most this many candidates.
MAX_CANDIDATES = 25

#: Printed on every lookup response.
SCOPE = (
    "This response reports what the sources under sources.checked contained as of "
    "each as_of date. Sources under sources.not_checked were not consulted. It is "
    "not a credentialing decision."
)

#: The source whose data fills the clinicians table this API answers from.
IDENTITY_SOURCE = "cms_dac"

_EXCLUSION_SOURCES = frozenset({"oig_leie", "sam_gov", "npdb_cq"})
_LICENSE_SOURCES = frozenset({"nursys", "fsmb_pdc"})
#: NPPES does not fill the identity block (the DAC file does); it is read to
#: link LEIE records that carry no NPI to NPIs by name and state.
_IDENTITY_SOURCES = frozenset({"cms_dac", "nppes", "nppes_weekly"})

_NOT_INGESTED = "No data from this source has been ingested."


def classify_source(key: str) -> SourceRole | None:
    """The part of a response a registry source feeds, or None if unused here."""
    if key in _IDENTITY_SOURCES:
        return "identity"
    if key in _EXCLUSION_SOURCES:
        return "exclusions"
    if key in _LICENSE_SOURCES or key.startswith("state_"):
        return "licenses"
    return None


def _status(source: SourceRecord, role: SourceRole, now: datetime) -> SourceStatus:
    checked = source.ingested
    reason = None if checked else _NOT_INGESTED
    expires = source.freshness_expires_at
    return SourceStatus(
        key=source.key,
        display_name=source.display_name,
        role=role,
        checked=checked,
        as_of=source.fetched_at,
        freshness_expires_at=expires,
        stale=bool(expires is not None and expires < now),
        freshness_sla_days=source.freshness_sla_days,
        reason_not_checked=reason,
    )


def build_sources_block(sources: Iterable[SourceRecord], now: datetime) -> SourcesBlock:
    """Split the registry into sources this API read and sources it did not."""
    checked: list[SourceStatus] = []
    not_checked: list[SourceStatus] = []
    for source in sources:
        role = classify_source(source.key)
        if role is None:
            continue
        status = _status(source, role, now)
        (checked if status.checked else not_checked).append(status)
    return SourcesBlock(checked=checked, not_checked=not_checked)


def _date(value: datetime | None) -> str:
    return value.astimezone(UTC).date().isoformat() if value is not None else "an unknown date"


def _name(status: SourceStatus) -> str:
    return status.display_name or status.key


def _join(names: Sequence[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _stale_sentences(statuses: Sequence[SourceStatus]) -> list[str]:
    return [
        f"The {_name(s)} snapshot fetched {_date(s.as_of)} is past its "
        f"{s.freshness_sla_days}-day freshness limit; changes published since then "
        f"are not reflected."
        for s in statuses
        if s.stale
    ]


def _leie_coverage(leie: SourceRecord | None) -> str:
    parsed: Mapping[str, object] = leie.parsed if leie is not None else {}
    total = parsed.get("rows_total")
    with_npi = parsed.get("rows_with_npi")
    name_dob = bool(parsed.get("name_dob_matching_enabled"))
    matching = (
        "name and date-of-birth matching is enabled"
        if name_dob
        else "name and date-of-birth matching is not enabled"
    )
    linked = parsed.get("rows_without_npi_with_candidates")
    if parsed.get("name_state_matching_ran") and isinstance(linked, int):
        name_state = (
            f" Of those, {linked:,} were linked by name and state to at least one NPPES NPI "
            "as possible matches for review; a possible match is never reported as an "
            "exclusion."
        )
    else:
        name_state = " Name and state matching against NPPES did not run for this snapshot."
    if isinstance(total, int) and isinstance(with_npi, int):
        return (
            f"{total - with_npi:,} of the {total:,} records in the OIG LEIE file carry no "
            f"NPI and cannot be matched on NPI, and {matching}.{name_state}"
        )
    return (
        "The share of OIG LEIE records that carry no NPI was not recorded by the ingest, "
        f"so the count not matched on NPI is unknown, and {matching}.{name_state}"
    )


def _exclusions(
    record: ClinicianRecord,
    block: SourcesBlock,
    registry: Mapping[str, SourceRecord],
) -> ExclusionScreen:
    screened = [s for s in block.checked if s.role == "exclusions"]
    unscreened = [s for s in block.not_checked if s.role == "exclusions"]
    matches = [
        ExclusionMatch(
            source=s.source,
            source_key=s.evidence_source_key,
            source_as_of=s.evidence_fetched_at,
            action_type=s.action_type,
            action_date=s.action_date,
            description=s.description,
            reinstated_date=s.reinstated_date,
            open=s.reinstated_date is None,
            match_basis=(
                "name_dob" if s.match_confidence is not None and s.match_confidence < 1 else "npi"
            ),
            match_confidence=s.match_confidence,
        )
        for s in record.sanctions
    ]
    possible = [
        PossibleExclusionMatch(
            status=(
                "confirmed_by_review"
                if p.review_status == "confirmed"
                else "possible_match_needs_review"
            ),
            source="leie",
            source_key=p.evidence_source_key,
            source_as_of=p.evidence_fetched_at,
            match_basis="name_state",
            match_confidence=p.match_confidence,
            match_detail={
                k: v for k, v in p.match_detail.items() if isinstance(v, str | int | float)
            },
            candidate_count=p.candidate_count,
            leie_last_name=p.leie_last_name,
            leie_first_name=p.leie_first_name,
            leie_middle_name=p.leie_middle_name,
            leie_state=p.leie_state,
            leie_specialty=p.leie_specialty,
            action_type=p.exclusion_type,
            action_date=p.exclusion_date,
            reinstated_date=p.reinstatement_date,
            open=p.reinstatement_date is None,
        )
        for p in record.possible_exclusions
    ]

    if not screened and not matches and not possible:
        return ExclusionScreen(
            status="not_screened",
            matches=[],
            sources_screened=[],
            note=(
                "No exclusion source has been ingested, so this clinician was not "
                "screened. This reports the absence of a screen, not the absence of "
                "an exclusion."
            ),
        )

    sentences: list[str] = []
    status: ExclusionStatus
    open_matches = [m for m in matches if m.open]
    if open_matches:
        status = "open_exclusion_found"
        sentences.append(
            f"{len(open_matches)} open exclusion record"
            f"{'' if len(open_matches) == 1 else 's'} matched this clinician. Each match "
            "lists its basis; a name and date-of-birth match is weaker evidence of "
            "identity than an NPI match and needs human review."
        )
    elif matches:
        status = "reinstated_exclusion_found"
        sentences.append(
            "Every exclusion record matched to this clinician carries a reinstatement date."
        )
    else:
        status = "possible_match_needs_review" if possible else "no_npi_match"
        sources_text = _join([f"{_name(s)} snapshot fetched {_date(s.as_of)}" for s in screened])
        sentences.append(f"No exclusion record matched this NPI in the {sources_text}.")
    if possible:
        sentences.append(
            f"{len(possible)} OIG LEIE record{'' if len(possible) == 1 else 's'} with no NPI "
            f"name{'s' if len(possible) == 1 else ''} someone with this clinician's name in a "
            "state tied to them. That is a name and state match only, with no date of birth "
            "compared: each is a possible match that needs human review, and none is "
            "asserted as an exclusion."
        )

    if any(s.key == "oig_leie" for s in screened):
        sentences.append(_leie_coverage(registry.get("oig_leie")))
    sentences.extend(_stale_sentences(screened))
    if unscreened:
        sentences.append(f"Not screened: {_join([_name(s) for s in unscreened])}.")
    if status in ("no_npi_match", "possible_match_needs_review"):
        sentences.append("This result does not establish that the clinician is not excluded.")

    return ExclusionScreen(
        status=status,
        matches=matches,
        possible_matches=possible,
        sources_screened=[s.key for s in screened],
        note=" ".join(sentences),
    )


def _licenses(record: ClinicianRecord, block: SourcesBlock) -> LicenseScreen:
    checked = [s for s in block.checked if s.role == "licenses"]
    records = [
        LicenseRecordOut(
            state=lic.state,
            license_type=lic.license_type,
            license_number=lic.license_number,
            status=lic.status,
            issued_on=lic.issue_date,
            expires_on=lic.expiry_date,
            is_compact=lic.is_compact,
            compact_home_state=lic.compact_home_state,
            discipline_reported=lic.discipline_reported,
            source_key=lic.evidence_source_key,
            source_as_of=lic.evidence_fetched_at,
            last_confirmed_at=lic.verified_at,
        )
        for lic in record.licenses
    ]
    if not checked and not records:
        return LicenseScreen(
            coverage="no_license_source_ingested",
            records=[],
            note=(
                "No license source has produced data in this system, so license status "
                "is unknown. No state board was checked."
            ),
        )

    names = _join([_name(s) for s in checked]) or "the ingested license sources"
    sentences: list[str]
    coverage: LicenseCoverage
    if records:
        coverage = "records_found"
        sentences = [f"License records as reported by {names}, as of the dates shown."]
    else:
        coverage = "no_records_found"
        sentences = [
            f"No license records for this clinician in {names}. This does not mean the "
            "clinician is unlicensed."
        ]
    if any(s.key == "nursys" for s in checked):
        sentences.append(
            "Nursys data covers only nurses enrolled through a client's Nursys account."
        )
    sentences.extend(_stale_sentences(checked))
    if not any(s.key.startswith("state_") for s in checked):
        sentences.append("No state board source was checked.")
    return LicenseScreen(coverage=coverage, records=records, note=" ".join(sentences))


def _standing(
    record: ClinicianRecord,
    block: SourcesBlock,
    registry: Mapping[str, SourceRecord],
    by_name: bool,
) -> ClinicianStanding:
    return ClinicianStanding(
        match_basis="name_state" if by_name else "npi",
        name_match="exact" if by_name else None,
        identity=Identity(
            npi=record.npi,
            first_name=record.first_name,
            middle_name=record.middle_name,
            last_name=record.last_name,
            suffix=record.suffix,
            credential=record.credential,
            clinician_type=record.clinician_type,
            primary_specialty=record.primary_specialty,
            practice_states=list(record.practice_states),
            source=IDENTITY_SOURCE,
        ),
        exclusions=_exclusions(record, block, registry),
        licenses=_licenses(record, block),
    )


def _not_found_note(request: CheckRequest) -> str:
    what = (
        "this NPI"
        if request.npi is not None
        else "this name with a practice or license in this state"
    )
    return (
        f"No clinician with {what} is in the ingested CMS Doctors and Clinicians data. "
        "Exclusion and license screens run only for clinicians in that data, so no "
        "screen was run."
    )


def check(
    store: StandingStore, request: CheckRequest, now: datetime | None = None
) -> StandingResponse:
    """Answer one lookup."""
    now = now or datetime.now(UTC)
    sources = store.list_sources()
    registry = {s.key: s for s in sources}
    block = build_sources_block(sources, now)

    by_name = request.npi is None
    truncated = False
    if request.npi is not None:
        found = store.get_by_npi(request.npi)
        records = [found] if found is not None else []
        query = {"npi": request.npi}
    else:
        assert request.last_name is not None and request.state is not None
        records = store.find_by_name(
            request.last_name, request.first_name, request.state, MAX_CANDIDATES + 1
        )
        truncated = len(records) > MAX_CANDIDATES
        records = records[:MAX_CANDIDATES]
        query = {"last_name": request.last_name, "state": request.state}
        if request.first_name is not None:
            query["first_name"] = request.first_name

    result: LookupResult
    if not records:
        result = "not_found"
    elif len(records) == 1:
        result = "found"
    else:
        result = "multiple_candidates"

    return StandingResponse(
        result=result,
        query=query,
        clinicians=[_standing(r, block, registry, by_name) for r in records],
        truncated=truncated,
        note=_not_found_note(request) if not records else None,
        checked_at=now,
        scope=SCOPE,
        sources=block,
    )


def sources_response(store: StandingStore, now: datetime | None = None) -> SourcesResponse:
    """The sources block on its own, for callers checking coverage before a lookup."""
    now = now or datetime.now(UTC)
    return SourcesResponse(
        checked_at=now,
        scope=SCOPE,
        sources=build_sources_block(store.list_sources(), now),
    )
