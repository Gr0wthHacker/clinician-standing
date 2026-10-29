"""Request and response shapes for the standing API.

Field names follow the license-check-hub spec where the concept is the same
(``issued_on``, ``expires_on``, ``checked_at``, ``name_match``). Where this
system knows less than that spec assumes, the shape says so in a field rather
than leaving a gap: every screen carries a status that distinguishes "looked and
found nothing" from "could not look".
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "CheckRequest",
    "ClinicianStanding",
    "ErrorBody",
    "ErrorResponse",
    "ExclusionMatch",
    "ExclusionScreen",
    "ExclusionStatus",
    "HealthResponse",
    "Identity",
    "LicenseCoverage",
    "LicenseRecordOut",
    "LicenseScreen",
    "LookupResult",
    "RosterClinician",
    "RosterEmployer",
    "RosterLicense",
    "RosterOutcome",
    "RosterReceipt",
    "RosterReviewStatus",
    "RosterSubmission",
    "SourceRole",
    "SourceStatus",
    "SourcesBlock",
    "SourcesResponse",
    "StandingResponse",
    "is_valid_npi",
    "normalize_name",
]

_NPI_RE = re.compile(r"^[0-9]{10}$")
_STATE_RE = re.compile(r"^[A-Z]{2}$")
_PAC_ID_RE = re.compile(r"^[0-9]{10}$")
_SOURCE_SYSTEM_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def is_valid_npi(value: str) -> bool:
    """True for a ten-digit NPI whose check digit is right.

    The check digit is the Luhn digit over ``80840`` plus the first nine digits
    (CMS, NPI check digit standard). Rejecting a typo here keeps a mistyped NPI
    from coming back as a reassuring ``not_found``.
    """
    if not _NPI_RE.match(value):
        return False
    digits = [int(d) for d in "80840" + value[:9]]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10 == int(value[9])


def normalize_name(value: str) -> str:
    """Upper-case and collapse whitespace, the way CMS spells names."""
    return " ".join(value.split()).upper()


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CheckRequest(BaseModel):
    """Look up by ``npi``, or by ``last_name`` plus ``state``."""

    npi: str | None = Field(default=None, examples=["1990000014"])
    last_name: str | None = Field(default=None, max_length=80, examples=["SAMPLE"])
    first_name: str | None = Field(default=None, max_length=80, examples=["ALPHA"])
    state: str | None = Field(
        default=None,
        description="Two-letter USPS code. Required with last_name.",
        examples=["MN"],
    )

    @field_validator("npi")
    @classmethod
    def _npi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not is_valid_npi(value):
            raise ValueError("npi must be 10 digits with a valid check digit")
        return value

    @field_validator("state")
    @classmethod
    def _state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not _STATE_RE.match(value):
            raise ValueError("state must be a two-letter code")
        return value

    @field_validator("last_name", "first_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = normalize_name(value)
        return value or None

    @model_validator(mode="after")
    def _one_mode(self) -> CheckRequest:
        by_name = self.last_name is not None or self.first_name is not None
        if self.npi is not None and by_name:
            raise ValueError("send npi, or last_name and state, not both")
        if self.npi is None:
            if self.last_name is None or self.state is None:
                raise ValueError("send npi, or last_name and state")
        elif self.state is not None:
            raise ValueError("state is only used with last_name")
        return self


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

SourceRole = Literal["identity", "exclusions", "licenses"]


class SourceStatus(BaseModel):
    """One source this API reads or would read, and how current it is."""

    key: str
    display_name: str | None
    role: SourceRole
    checked: bool = Field(description="True when this response read data ingested from the source.")
    as_of: datetime | None = Field(
        description="When the newest ingested snapshot of the source was fetched."
    )
    freshness_expires_at: datetime | None
    stale: bool = Field(description="True when as_of is past the source's freshness limit.")
    freshness_sla_days: int
    reason_not_checked: str | None = None


class SourcesBlock(BaseModel):
    """Which sources this answer rests on, and which it does not."""

    checked: list[SourceStatus]
    not_checked: list[SourceStatus]


# ---------------------------------------------------------------------------
# Clinician standing
# ---------------------------------------------------------------------------


class Identity(BaseModel):
    npi: str
    first_name: str | None
    middle_name: str | None
    last_name: str | None
    suffix: str | None
    credential: str | None
    clinician_type: str
    primary_specialty: str | None
    practice_states: list[str] = Field(
        description="States of the practices CMS lists this clinician at (active affiliations)."
    )
    source: str = Field(description="Registry key of the source the identity comes from.")


class ExclusionMatch(BaseModel):
    source: str = Field(description="leie | sam | npdb | state_board")
    source_key: str | None = Field(description="Registry key of the evidence row.")
    source_as_of: datetime | None = Field(description="Fetch time of that evidence row.")
    action_type: str | None
    action_date: date | None
    description: str | None
    reinstated_date: date | None
    open: bool = Field(description="True when no reinstatement date is recorded.")
    match_basis: Literal["npi", "name_dob"]
    match_confidence: float | None


ExclusionStatus = Literal[
    "open_exclusion_found",
    "reinstated_exclusion_found",
    "no_npi_match",
    "not_screened",
]


class ExclusionScreen(BaseModel):
    status: ExclusionStatus
    matches: list[ExclusionMatch]
    sources_screened: list[str]
    note: str


LicenseCoverage = Literal["no_license_source_ingested", "no_records_found", "records_found"]


class LicenseRecordOut(BaseModel):
    state: str
    license_type: str
    license_number: str | None
    status: str = Field(description="active | expired | lapsed | suspended | revoked | probation")
    issued_on: date | None
    expires_on: date | None
    is_compact: bool
    compact_home_state: str | None
    discipline_reported: bool | None = Field(
        description="Whether the source reported discipline, when it says. Null means unknown."
    )
    source_key: str | None
    source_as_of: datetime | None
    last_confirmed_at: datetime = Field(
        description="When the ingest last matched this record to the source's evidence."
    )


class LicenseScreen(BaseModel):
    coverage: LicenseCoverage
    records: list[LicenseRecordOut]
    note: str


class ClinicianStanding(BaseModel):
    match_basis: Literal["npi", "name_state"]
    name_match: Literal["exact"] | None = Field(
        description="Set for name lookups. Matching is exact on the normalized name."
    )
    identity: Identity
    exclusions: ExclusionScreen
    licenses: LicenseScreen


LookupResult = Literal["found", "not_found", "multiple_candidates"]


class StandingResponse(BaseModel):
    result: LookupResult
    query: dict[str, str]
    clinicians: list[ClinicianStanding]
    truncated: bool = Field(description="True when more candidates matched than were returned.")
    note: str | None = Field(default=None, description="Set when result is not_found.")
    checked_at: datetime
    scope: str
    sources: SourcesBlock


class SourcesResponse(BaseModel):
    checked_at: datetime
    scope: str
    sources: SourcesBlock


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------------------------------------------------------------------------
# Roster intake
#
# A placement system hands a placed clinician to the roster. Every model here
# forbids unknown fields, so a caller cannot slip a date of birth, an email or
# anything else past the schema: the request fails instead (PRD 2, no PHI).
# ---------------------------------------------------------------------------


def _usps(value: str) -> str:
    value = value.strip().upper()
    if not _STATE_RE.match(value):
        raise ValueError("state must be a two-letter code")
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class RosterLicense(BaseModel):
    """A license as the caller reports it. Recorded as a claim, never as evidence."""

    model_config = ConfigDict(extra="forbid")

    state: str = Field(examples=["MN"])
    license_type: str = Field(min_length=1, max_length=40, examples=["RN"])
    license_number: str | None = Field(default=None, max_length=40)
    expires_on: date | None = None

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        return _usps(value)

    @field_validator("license_type")
    @classmethod
    def _type(cls, value: str) -> str:
        cleaned = normalize_name(value)
        if not cleaned:
            raise ValueError("license_type must not be blank")
        return cleaned

    @field_validator("license_number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return _optional_text(value)


class RosterClinician(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, max_length=80, examples=["ALPHA"])
    last_name: str = Field(max_length=80, examples=["SAMPLE"])
    npi: str | None = Field(default=None, description="Send it when known.")
    credential: str | None = Field(default=None, max_length=20, examples=["RN"])

    @field_validator("npi")
    @classmethod
    def _npi(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not is_valid_npi(value):
            raise ValueError("npi must be 10 digits with a valid check digit")
        return value

    @field_validator("first_name", "credential")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_name(value) or None

    @field_validator("last_name")
    @classmethod
    def _last(cls, value: str) -> str:
        cleaned = normalize_name(value)
        if not cleaned:
            raise ValueError("last_name must not be blank")
        return cleaned


class RosterEmployer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200, examples=["SAMPLE TEST CLINIC"])
    org_pac_id: str | None = Field(default=None, description="CMS group PAC ID, when known.")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = _optional_text(value)
        if cleaned is None:
            raise ValueError("employer name must not be blank")
        return cleaned

    @field_validator("org_pac_id")
    @classmethod
    def _pac(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _PAC_ID_RE.match(value):
            raise ValueError("org_pac_id must be 10 digits")
        return value


class RosterSubmission(BaseModel):
    """One placed clinician. ``(source_system, external_id)`` is the idempotency key:
    resending it updates the same row, and an identical resend changes nothing."""

    model_config = ConfigDict(extra="forbid")

    source_system: str = Field(examples=["placerail"])
    external_id: str = Field(
        min_length=1, max_length=128, description="The caller's own id, e.g. a placement id."
    )
    clinician: RosterClinician
    licenses: list[RosterLicense] = Field(default_factory=list, max_length=50)
    states: list[str] = Field(
        default_factory=list,
        max_length=60,
        description="States the clinician works or is licensed in. License states are added.",
    )
    employer: RosterEmployer
    employment_status: Literal["active", "ended"] = "active"
    placed_on: date | None = None

    @field_validator("source_system")
    @classmethod
    def _source(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SOURCE_SYSTEM_RE.match(value):
            raise ValueError("source_system must be 2-32 lowercase letters, digits or _")
        return value

    @field_validator("external_id")
    @classmethod
    def _external(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("external_id must not be blank")
        return value

    @field_validator("states")
    @classmethod
    def _states(cls, value: list[str]) -> list[str]:
        return sorted({_usps(v) for v in value})

    @model_validator(mode="after")
    def _license_states(self) -> RosterSubmission:
        self.states = sorted(set(self.states) | {lic.state for lic in self.licenses})
        return self

    def digest(self) -> str:
        """sha256 over the normalized submission, for "did anything change"."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


RosterOutcome = Literal["created", "updated", "unchanged"]
RosterReviewStatus = Literal["pending", "matched", "rejected"]


class RosterReceipt(BaseModel):
    id: str
    source_system: str
    external_id: str
    outcome: RosterOutcome = Field(
        description="created (201), or updated / unchanged (200) for a resend."
    )
    review_status: RosterReviewStatus
    received_at: datetime
    updated_at: datetime
    note: str
