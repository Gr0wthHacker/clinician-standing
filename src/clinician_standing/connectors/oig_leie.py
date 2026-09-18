"""OIG List of Excluded Individuals and Entities (LEIE).

An exclusion is the highest-consequence fact this system can assert. A clinician
on the LEIE cannot be paid by any federal health care program, and a practice
that bills for their services is exposed to civil monetary penalties. Section
8.3 routes a hit to ``HIGH_CONSEQUENCE``, same day, account lead notified.

Two properties of the file drive the code below.

**It is latin-1, not UTF-8.** Opening ``UPDATED.csv`` with the default encoding
raises ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa0``. 0xa0 is a
non-breaking space that appears inside names and addresses. This is not a
theoretical edge case; it is the first thing that breaks when the file is read
naively, and it is why :data:`FILE_ENCODING` is set explicitly rather than left
to the platform default.

**NPI coverage is about 10%.** Roughly 8,701 of 84,001 rows carry an NPI, and
the rest carry only name, date of birth, address and business name. NPI-only
matching therefore finds almost nothing. NPI matching is implemented here and is
the only matching that ships; name plus date-of-birth matching is stubbed and
gated, see :func:`match_by_name_dob`.

Populates ``sanctions`` with ``match_confidence`` 1.0 for an NPI match.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import insert_credential, json_payload, store_evidence, store_evidence_for_file
from .base import Connector, ConnectorError, DiffResult

__all__ = ["FILE_ENCODING", "LEIE_URL", "OigLeieConnector", "match_by_name_dob"]

#: Monthly full replacement file. OIG also publishes monthly add/delete
#: supplements; this connector takes the full file, which is simpler and only
#: 15.6 MB.
LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"

#: OIG publishes this file in latin-1 (ISO-8859-1). Reading it as UTF-8 fails at
#: byte 0xa0. Do not "fix" this by switching to utf-8 with errors="replace";
#: that silently corrupts names in an exclusion file, which is the one place
#: corruption is least acceptable.
FILE_ENCODING = "latin-1"

COL_LASTNAME = "LASTNAME"
COL_FIRSTNAME = "FIRSTNAME"
COL_MIDNAME = "MIDNAME"
COL_BUSNAME = "BUSNAME"
COL_GENERAL = "GENERAL"
COL_SPECIALTY = "SPECIALTY"
COL_UPIN = "UPIN"
COL_NPI = "NPI"
COL_DOB = "DOB"
COL_ADDRESS = "ADDRESS"
COL_CITY = "CITY"
COL_STATE = "STATE"
COL_ZIP = "ZIP"
COL_EXCLTYPE = "EXCLTYPE"
COL_EXCLDATE = "EXCLDATE"
COL_REINDATE = "REINDATE"
COL_WAIVERDATE = "WAIVERDATE"
COL_WVRSTATE = "WVRSTATE"

REQUIRED_COLUMNS: tuple[str, ...] = (
    COL_LASTNAME,
    COL_FIRSTNAME,
    COL_BUSNAME,
    COL_NPI,
    COL_DOB,
    COL_EXCLTYPE,
    COL_EXCLDATE,
    COL_REINDATE,
)

#: OIG writes a missing NPI as ten zeros rather than leaving the field empty.
NPI_PLACEHOLDER = "0000000000"

#: OIG writes a missing date as eight zeros.
DATE_PLACEHOLDER = "00000000"

#: Set to True only when name+DOB matching has been reviewed by counsel and has
#: a tested confidence threshold. See :func:`match_by_name_dob`.
NAME_DOB_MATCHING_ENABLED = False

STAGING_COLUMNS: tuple[str, ...] = (
    "last_name",
    "first_name",
    "middle_name",
    "business_name",
    "general_category",
    "specialty",
    "upin",
    "npi",
    "dob_hash",
    "address",
    "city",
    "state",
    "zip",
    "exclusion_type",
    "exclusion_date",
    "reinstatement_date",
    "waiver_date",
    "waiver_state",
)

_CREATE_STAGING = """
create temporary table stg_oig_leie (
    last_name          text,
    first_name         text,
    middle_name        text,
    business_name      text,
    general_category   text,
    specialty          text,
    upin               text,
    npi                text,
    dob_hash           text,
    address            text,
    city               text,
    state              text,
    zip                text,
    exclusion_type     text,
    exclusion_date     date,
    reinstatement_date date,
    waiver_date        date,
    waiver_state       text
) on commit drop
"""

_SELECT_NPI_MATCHES = """
select
    c.id, c.npi, s.last_name, s.first_name, s.middle_name, s.business_name,
    s.general_category, s.specialty, s.exclusion_type, s.exclusion_date,
    s.reinstatement_date, s.waiver_date, s.waiver_state, s.address, s.city,
    s.state, s.zip, s.dob_hash
from stg_oig_leie s
join clinicians c on c.npi = s.npi
where s.npi is not null
"""

_SANCTION_EXISTS = """
select 1 from sanctions
where clinician_id = %(clinician_id)s
  and source = 'leie'
  and action_type is not distinct from %(action_type)s
  and action_date is not distinct from %(action_date)s
limit 1
"""


def _clean(value: str | None) -> str:
    """Trim a field, mapping None to empty string."""
    return (value or "").strip()


def _parse_npi(value: str) -> str | None:
    """Return a usable NPI, or None for OIG's ten-zero placeholder."""
    npi = _clean(value)
    if not npi or npi == NPI_PLACEHOLDER or set(npi) == {"0"}:
        return None
    return npi


def _parse_date(value: str) -> date | None:
    """Parse OIG's ``YYYYMMDD`` dates, treating ``00000000`` as absent."""
    raw = _clean(value)
    if not raw or raw == DATE_PLACEHOLDER or set(raw) == {"0"}:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def dob_hash(birth_date: date | None) -> str | None:
    """Hash a date of birth the same way ``clinicians.dob_hash`` is built.

    The schema stores only a hash so a raw date of birth never sits in the
    roster. Both sides must use the same normalization or the future name+DOB
    match will never fire.

    Args:
        birth_date: Date of birth, or None.

    Returns:
        Hex sha256 of the ISO-8601 date, or None.
    """
    if birth_date is None:
        return None
    return hashlib.sha256(birth_date.isoformat().encode("utf-8")).hexdigest()


def match_by_name_dob(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Name + date-of-birth matching against the roster. **Not implemented.**

    TODO(fcra-counsel): about 90% of LEIE rows carry no NPI, so this is the
    matching that would actually find most exclusions. It is deliberately not
    shipped yet.

    A false positive here is not a data-quality blemish. It is a recorded
    accusation, against a named clinician, that they are excluded from federal
    health care programs -- reported to their employer. PRD section 13 flags
    that reporting this to an employer may make it a consumer report under
    FCRA, and section 15 open decision 3 says the threshold has to be measured
    before it ships.

    What has to exist before this function is written:

    * a tested confidence threshold with a measured false-positive rate on a
      labeled sample, not a guessed similarity cutoff;
    * agreement on what a sub-1.0 ``match_confidence`` is allowed to do. It must
      never auto-clear (section 8.1 requires a strong single key) and should
      raise ``IDENTITY_AMBIGUOUS`` or ``HIGH_CONSEQUENCE`` for a human;
    * counsel sign-off on the FCRA classification, which is a precondition for
      the first paying account regardless;
    * ``clinicians.dob_hash`` populated for the roster. Hashed DOB supports only
      exact date matching; fuzzy DOB would need a different storage decision and
      its own privacy review.

    Args:
        rows: Parsed LEIE rows with no NPI.

    Raises:
        NotImplementedError: Always, until the above are in place.
    """
    raise NotImplementedError(
        "LEIE name+DOB matching is not implemented. It needs a tested confidence "
        "threshold and counsel review before a sub-1.0 match may be recorded "
        "against a named clinician. See TODO(fcra-counsel)."
    )


class OigLeieConnector(Connector):
    """Ingest the OIG LEIE exclusions file and record NPI-matched sanctions."""

    key: ClassVar[str] = "oig_leie"
    display_name: ClassVar[str] = "OIG List of Excluded Individuals and Entities"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    # 45 days, matching the seeded registry row. The registry is
    # authoritative and ensure_registered() adopts its value at run time;
    # this is only the value used against a database with no seed.
    freshness_sla_days: int = 45
    # Same rule as freshness_sla_days: 0009_seed_sources.sql seeds this flag,
    # 0010_source_attestation.sql pairs it with attests_obligation_types, and
    # ensure_registered() adopts the registry's value at run time.
    #
    # true. OIG publishes the LEIE and IS the authoritative record of exclusion
    # from federal health care programs; 0010 corrected this from the seed's
    # original false, which had made it impossible for the monthly
    # exclusion_screen obligation to ever auto-clear. It attests to
    # exclusion_screen and to nothing else.
    is_primary_source: bool = True
    terms_url: ClassVar[str | None] = "https://oig.hhs.gov/exclusions/index.asp"

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the connector and its per-run counters."""
        super().__init__(settings)
        self.rows_total: int = 0
        self.rows_with_npi: int = 0
        self.rows_individual: int = 0

    # ----------------------------------------------------------------- fetch

    def fetch(self) -> Path:
        """Download the current full exclusions file.

        Returns:
            Path to the local CSV.
        """
        override = self.settings.local_source_override(self.key)
        if override is not None:
            self.request_ref = f"file://{override}"
            # The operator owns this file; _cleanup() must not delete it.
            self.fetched_is_external = True
            self.log.warning("using LOCAL_SOURCE override %s instead of fetching", override)
            return override
        self.request_ref = LEIE_URL
        return self.download(LEIE_URL, self.work_file("UPDATED.csv"))

    # ----------------------------------------------------------------- parse

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream normalized exclusion rows.

        Args:
            path: Local CSV.

        Yields:
            Normalized row dicts.

        Raises:
            ConnectorError: If OIG changed the header.
        """
        self.rows_total = 0
        self.rows_with_npi = 0
        self.rows_individual = 0

        # encoding is latin-1 on purpose; see FILE_ENCODING.
        with path.open("r", encoding=FILE_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ConnectorError(
                    f"LEIE header changed; missing columns {missing}. Saw: {reader.fieldnames}"
                )
            for raw in reader:
                self.rows_total += 1
                npi = _parse_npi(raw.get(COL_NPI, ""))
                if npi:
                    self.rows_with_npi += 1
                last_name = _clean(raw.get(COL_LASTNAME))
                if last_name:
                    self.rows_individual += 1
                birth_date = _parse_date(raw.get(COL_DOB, ""))
                yield {
                    "last_name": last_name or None,
                    "first_name": _clean(raw.get(COL_FIRSTNAME)) or None,
                    "middle_name": _clean(raw.get(COL_MIDNAME)) or None,
                    "business_name": _clean(raw.get(COL_BUSNAME)) or None,
                    "general_category": _clean(raw.get(COL_GENERAL)) or None,
                    "specialty": _clean(raw.get(COL_SPECIALTY)) or None,
                    "upin": _clean(raw.get(COL_UPIN)) or None,
                    "npi": npi,
                    "dob_hash": dob_hash(birth_date),
                    "address": _clean(raw.get(COL_ADDRESS)) or None,
                    "city": _clean(raw.get(COL_CITY)) or None,
                    "state": _clean(raw.get(COL_STATE))[:2] or None,
                    "zip": _clean(raw.get(COL_ZIP)) or None,
                    "exclusion_type": _clean(raw.get(COL_EXCLTYPE)) or None,
                    "exclusion_date": _parse_date(raw.get(COL_EXCLDATE, "")),
                    "reinstatement_date": _parse_date(raw.get(COL_REINDATE, "")),
                    "waiver_date": _parse_date(raw.get(COL_WAIVERDATE, "")),
                    "waiver_state": _clean(raw.get(COL_WVRSTATE))[:2] or None,
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """Identity of an exclusion row.

        NPI is used when present. Otherwise the identity is the name, hashed
        date of birth and business name together with the exclusion date, which
        is the closest thing to a stable key the file offers. The key needs
        stability, not a readable date, so the hash serves and the raw date of
        birth never leaves :meth:`parse`. This is for change detection between
        runs only; it is never used to assert that a row is a particular
        clinician.
        """
        parts = [
            "npi" if row.get("npi") else "name",
            row.get("npi") or "",
            row.get("last_name") or "",
            row.get("first_name") or "",
            row.get("middle_name") or "",
            row.get("dob_hash") or "",
            row.get("business_name") or "",
            str(row.get("exclusion_date") or ""),
            # Address is part of the key because OIG lists a single excluded
            # business once per location: same name, same exclusion date,
            # different address. Without it those rows collide.
            row.get("address") or "",
            row.get("city") or "",
            row.get("state") or "",
            row.get("zip") or "",
        ]
        return "|".join(parts)

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Fields whose movement counts as a change."""
        return (
            row.get("exclusion_type"),
            row.get("exclusion_date"),
            row.get("reinstatement_date"),
            row.get("waiver_date"),
            row.get("waiver_state"),
            row.get("general_category"),
            row.get("specialty"),
            row.get("address"),
            row.get("city"),
            row.get("state"),
            row.get("zip"),
        )

    # ------------------------------------------------------------------ load

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then per-match evidence and sanction rows.

        Unlike the other bulk connectors, evidence here is written per matched
        clinician as well as per file. An exclusion is asserted about a named
        person, so the audit trail has to show exactly which LEIE row was matched
        and by which key, not just that a file was downloaded that day.

        **Screening scope is the whole file, not the change set.** PRD section 7
        requires a monthly exclusion screen against every clinician on the
        roster. An NPI that was already excluded last month produces no diff row
        this month, so staging only ``diff.iter_rows()`` would never match it
        against a clinician onboarded since -- the exclusion would be invisible
        for as long as the roster kept growing. The full parsed file is staged
        every run (84,001 rows) and the entire roster is screened against it.
        The diff is kept for reporting ``rows_new``/``rows_changed`` only.

        Args:
            diff: Change set from :meth:`diff`, used for reporting.
        """
        if self.fetched_path is None or self.fetched_checksum is None:
            raise ConnectorError("load() called before fetch()")

        npi_coverage = round(self.rows_with_npi / self.rows_total, 4) if self.rows_total else 0.0
        self.log.info(
            "LEIE rows=%s with_npi=%s (%.1f%%)",
            f"{self.rows_total:,}",
            f"{self.rows_with_npi:,}",
            npi_coverage * 100,
        )

        with transaction(None, self.settings) as conn:
            self.ensure_registered(conn)
            file_evidence_id = store_evidence_for_file(
                self.key,
                self.request_ref,
                self.fetched_path,
                parsed={
                    "rows_total": self.rows_total,
                    "rows_with_npi": self.rows_with_npi,
                    "rows_individual": self.rows_individual,
                    "npi_coverage": npi_coverage,
                    "encoding": FILE_ENCODING,
                    "rows_new": diff.rows_new,
                    "rows_changed": diff.rows_changed,
                    "name_dob_matching_enabled": NAME_DOB_MATCHING_ENABLED,
                },
                match_keys={"npi": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = file_evidence_id

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            # The full file, re-parsed -- not diff.iter_rows(). See the note on
            # screening scope in this method's docstring.
            staged = copy_from_csv(
                conn,
                "stg_oig_leie",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in self.parse(self.fetched_path)),
                batch_size=self.settings.copy_batch_size,
            )
            self.log.info(
                "staged %s LEIE rows for a full-roster screen (new=%s changed=%s this run)",
                f"{staged:,}",
                f"{diff.rows_new:,}",
                f"{diff.rows_changed:,}",
            )
            with conn.cursor() as cur:
                cur.execute("create index on stg_oig_leie (npi)")
                cur.execute("analyze stg_oig_leie")

            matches = self._npi_matches(conn)
            self.log.info("LEIE NPI matches against the roster: %s", len(matches))
            written = 0
            for match in matches:
                if self._record_sanction(conn, match, file_evidence_id):
                    written += 1
            self.log.info("sanction rows written: %s", written)

            if not NAME_DOB_MATCHING_ENABLED:
                # Stated explicitly in the run log so nobody reads "0 matches"
                # as "0 exclusions". ~90% of the file cannot be matched yet.
                self.log.warning(
                    "name+DOB matching is disabled; %s of %s LEIE rows carry no NPI and "
                    "were not screened. See TODO(fcra-counsel) in oig_leie.py",
                    f"{self.rows_total - self.rows_with_npi:,}",
                    f"{self.rows_total:,}",
                )

    def _npi_matches(self, conn: Any) -> list[dict[str, Any]]:
        """Return staged exclusion rows whose NPI is on the roster."""
        with conn.cursor() as cur:
            cur.execute(_SELECT_NPI_MATCHES)
            columns = [d.name for d in cur.description or []]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    def _record_sanction(self, conn: Any, match: dict[str, Any], file_evidence_id: Any) -> bool:
        """Write one sanction row with its own evidence, if not already present.

        Args:
            conn: Open connection inside a transaction.
            match: Joined staging row plus ``clinicians.id``.
            file_evidence_id: Evidence for the whole file, referenced from the
                per-match evidence so the chain back to the raw payload is intact.

        Returns:
            True when a sanction row was written.
        """
        clinician_id = match["id"]
        action_type = match.get("exclusion_type")
        action_date = match.get("exclusion_date")

        with conn.cursor() as cur:
            cur.execute(
                _SANCTION_EXISTS,
                {
                    "clinician_id": clinician_id,
                    "action_type": action_type,
                    "action_date": action_date,
                },
            )
            if cur.fetchone():
                return False

        record = {k: v for k, v in match.items() if k != "id"}
        evidence_id = store_evidence(
            self.key,
            self.request_ref,
            json_payload(record),
            parsed=record,
            match_keys={
                "npi": match.get("npi"),
                "method": "npi_exact",
                "match_confidence": 1.0,
                "source_payload_sha256": self.fetched_checksum,
                "file_evidence_id": str(file_evidence_id),
            },
            freshness_days=self.freshness_sla_days,
            conn=conn,
            fetched_at=self.fetched_at,
            settings=self.settings,
            suffix=".json",
        )

        # 0003_credentials.sql enforces reinstated_date >= action_date. A LEIE row
        # that violates it must not abort the whole transaction and lose every
        # other exclusion in the batch: the exclusion is the fact that matters,
        # the reinstatement date is metadata. Drop the date, log it, and leave
        # the raw row intact in this match's evidence payload.
        reinstated = match.get("reinstatement_date")
        if reinstated and action_date and reinstated < action_date:
            self.log.warning(
                "LEIE row for NPI %s has reinstatement %s before exclusion %s; "
                "recording the exclusion without the reinstatement date",
                match.get("npi"),
                reinstated,
                action_date,
            )
            reinstated = None

        description_parts = [
            p for p in (match.get("general_category"), match.get("specialty")) if p
        ]
        insert_credential(
            conn,
            "sanctions",
            {
                "clinician_id": clinician_id,
                "source": "leie",
                "action_type": action_type,
                "action_date": action_date,
                "description": " / ".join(description_parts) or None,
                "reinstated_date": reinstated,
                # 1.0 means the identity was matched on NPI, a strong single key.
                # Anything below 1.0 will mean a name/DOB match and must never
                # auto-clear (PRD 8.1).
                "match_confidence": 1.0,
            },
            evidence_id,
        )
        return True
