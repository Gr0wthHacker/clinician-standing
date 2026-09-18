"""CMS Revalidation Clinic Group Practice Reassignment file.

About 540 MB and 3.39M rows, refreshed monthly. One row per individual
reassignment of billing rights to a group, carrying the group's PAC ID and
revalidation due date alongside the individual's NPI and due date.

This is the file that makes the free roster audit (PRD section 9) work: it joins
straight to ``practices.org_pac_id`` and it is how the pipeline found 5,614
practices with overdue group revalidations across the 10,211-practice target
list.

Two gotchas:

* **latin-1 encoded**, like the LEIE file. Group legal business names carry
  bytes that are not valid UTF-8, and reading with the default encoding raises
  ``UnicodeDecodeError``.
* **The URL is dated and moves monthly.** It is discovered from
  ``https://data.cms.gov/data.json`` by dataset title, taking the newest CSV
  distribution, rather than hardcoding a path under ``/sites/default/files/<ym>/``.

Populates ``enrollments`` with ``payer='medicare'`` and ``revalidation_due``.

``enrollments.status`` is **not** computed from the due date here. A status
derived from a date and "today" is stale the moment it is stored, and this file
only revisits a row when CMS changes it, so a due date that passes in a quiet
month would leave the row reading ``approved`` indefinitely. The connector
writes the published due date; ``db/migrations/0012_enrollment_status_view.sql``
adds ``enrollments_current``, which derives ``status_current`` from
``revalidation_due`` against ``current_date`` every time it is read. Read the
view, not ``enrollments.status``.
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import require_evidence, store_evidence_for_file
from .base import Connector, ConnectorError, DiffResult

__all__ = ["DATASET_TITLE", "DATA_JSON_URL", "FILE_ENCODING", "CmsRevalidationConnector"]

#: CMS's DCAT catalog of every public dataset.
DATA_JSON_URL = "https://data.cms.gov/data.json"

#: Exact dataset title in the catalog.
DATASET_TITLE = "Revalidation Clinic Group Practice Reassignment"

#: See the module docstring. Same failure mode as the LEIE file.
FILE_ENCODING = "latin-1"

COL_GROUP_PAC_ID = "Group PAC ID"
COL_GROUP_ENROLLMENT_ID = "Group Enrollment ID"
COL_GROUP_LEGAL_NAME = "Group Legal Business Name"
COL_GROUP_STATE = "Group State Code"
COL_GROUP_DUE_DATE = "Group Due Date"
COL_GROUP_REASSIGNMENTS = "Group Reassignments and Physician Assistants"
COL_RECORD_TYPE = "Record Type"
COL_IND_ENROLLMENT_ID = "Individual Enrollment ID"
COL_IND_NPI = "Individual NPI"
COL_IND_FIRST_NAME = "Individual First Name"
COL_IND_LAST_NAME = "Individual Last Name"
COL_IND_STATE = "Individual State Code"
COL_IND_SPECIALTY = "Individual Specialty Description"
COL_IND_DUE_DATE = "Individual Due Date"
COL_IND_TOTAL_EMPLOYER_ASSOCIATIONS = "Individual Total Employer Associations"

REQUIRED_COLUMNS: tuple[str, ...] = (
    COL_GROUP_PAC_ID,
    COL_GROUP_LEGAL_NAME,
    COL_GROUP_DUE_DATE,
    COL_IND_NPI,
    COL_IND_DUE_DATE,
    COL_IND_TOTAL_EMPLOYER_ASSOCIATIONS,
)

#: CMS writes "TBD" in a due-date column when no revalidation date is assigned.
#: It is not a null and it is not a date; treat it as "no due date known".
DUE_DATE_UNKNOWN = {"TBD", "", "N/A", "NA"}

#: Due dates are MM/DD/YYYY in this file, unlike the LEIE file's YYYYMMDD.
DUE_DATE_FORMAT = "%m/%d/%Y"

STAGING_COLUMNS: tuple[str, ...] = (
    "group_pac_id",
    "group_enrollment_id",
    "group_legal_business_name",
    "group_state",
    "group_due_date",
    "group_reassignments",
    "record_type",
    "individual_enrollment_id",
    "individual_npi",
    "individual_first_name",
    "individual_last_name",
    "individual_state",
    "individual_specialty",
    "individual_due_date",
    "individual_total_employer_associations",
)

_CREATE_STAGING = """
create temporary table stg_cms_revalidation (
    group_pac_id                           text,
    group_enrollment_id                    text,
    group_legal_business_name              text,
    group_state                            text,
    group_due_date                         date,
    group_reassignments                    integer,
    record_type                            text,
    individual_enrollment_id               text,
    individual_npi                         text,
    individual_first_name                  text,
    individual_last_name                   text,
    individual_state                       text,
    individual_specialty                   text,
    individual_due_date                    date,
    individual_total_employer_associations integer
) on commit drop
"""

# One row per (individual NPI, group PAC ID). The file can repeat a pair across
# record types, so collapse before touching enrollments.
#
# The `distinct on ... order by individual_due_date nulls last` below only picks
# the right row when stg_cms_revalidation holds EVERY row for the pair. On the
# real file 1,048 pairs carry more than one distinct due date and 1,035 of those
# mix a real date with TBD (which parses to NULL). Staged from a change set,
# a month in which only the TBD row moved would leave the NULL as the pair's
# only row, and _UPDATE_ENROLLMENTS would overwrite a genuine past-due date with
# NULL -- erasing the only input the enrollments_current view has, so the
# clinician would read as 'approved' while past due. load() therefore stages the
# full current file, never diff.iter_rows().
_CREATE_PAIRS = """
create temporary table stg_reval_pairs on commit drop as
select distinct on (individual_npi, group_pac_id)
    individual_npi, group_pac_id, individual_due_date, group_due_date,
    individual_enrollment_id, individual_total_employer_associations
from stg_cms_revalidation
where individual_npi is not null and individual_npi <> ''
  and group_pac_id is not null and group_pac_id <> ''
order by individual_npi, group_pac_id, individual_due_date nulls last
"""

# STATUS IS NOT DERIVED FROM A DATE HERE. See db/migrations/0012.
#
# These statements used to compute
#
#     case when p.individual_due_date < current_date then 'revalidation_due'
#          else 'approved' end
#
# and store the answer. current_date moves; a stored answer does not, and this
# file is monthly and only reaches a row when CMS changes something in it. A
# clinician whose due date passed during a month in which CMS changed nothing
# about their row kept status = 'approved' while being past due, and kept it
# until CMS happened to touch the row again. PRD 7 rates a past-due Medicare
# revalidation on a billing clinician critical severity.
#
# What this connector writes now is the fact CMS actually publishes: the due
# date. `status` is written as 'approved', which is what a live reassignment of
# billing rights in the current file asserts and is not a function of today's
# date. Anything that has to know whether the revalidation is overdue reads the
# `enrollments_current` view, which derives it at read time.
_ENROLLMENT_STATUS = "'approved'"

_UPDATE_ENROLLMENTS = f"""
update enrollments e set
    status           = {_ENROLLMENT_STATUS},
    revalidation_due = p.individual_due_date,
    evidence_id      = %(evidence_id)s,
    verified_at      = %(verified_at)s
from stg_reval_pairs p
join clinicians c on c.npi = p.individual_npi
join practices  pr on pr.org_pac_id = p.group_pac_id
where e.clinician_id = c.id
  and e.practice_id = pr.id
  and e.payer = 'medicare'
"""

_INSERT_ENROLLMENTS = f"""
insert into enrollments (
    id, clinician_id, practice_id, payer, status, revalidation_due,
    evidence_id, verified_at
)
select
    gen_random_uuid(), c.id, pr.id, 'medicare', {_ENROLLMENT_STATUS},
    p.individual_due_date, %(evidence_id)s, %(verified_at)s
from stg_reval_pairs p
join clinicians c on c.npi = p.individual_npi
join practices  pr on pr.org_pac_id = p.group_pac_id
where not exists (
    select 1 from enrollments e
    where e.clinician_id = c.id and e.practice_id = pr.id and e.payer = 'medicare'
)
"""


def _clean(value: str | None) -> str:
    """Trim a field, mapping None to empty string."""
    return (value or "").strip()


def _parse_due_date(value: str | None) -> date | None:
    """Parse a CMS revalidation due date.

    Args:
        value: Raw cell, ``MM/DD/YYYY`` or ``TBD``.

    Returns:
        The date, or None when CMS has not assigned one.
    """
    raw = _clean(value).upper()
    if raw in DUE_DATE_UNKNOWN:
        return None
    try:
        return datetime.strptime(_clean(value), DUE_DATE_FORMAT).date()
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    """Parse an integer cell, returning None when it is not one."""
    raw = _clean(value)
    return int(raw) if raw.isdigit() else None


class CmsRevalidationConnector(Connector):
    """Ingest the CMS revalidation reassignment file into ``enrollments``."""

    key: ClassVar[str] = "cms_revalidation"
    display_name: ClassVar[str] = "CMS Revalidation Clinic Group Practice Reassignment"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    freshness_sla_days: int = 45
    # The registry is authoritative for this flag: 0009_seed_sources.sql seeds
    # it and 0010_source_attestation.sql pairs it with
    # attests_obligation_types. ensure_registered() adopts the registry's value
    # at run time, exactly as it does for freshness_sla_days, so this
    # declaration is only what a database with no row for cms_revalidation
    # would get.
    #
    # true. CMS is the authority on Medicare enrollment and revalidation, so
    # this file is a primary source for the medicare_revalidation obligation
    # and for nothing else -- which is what 0010 records in
    # attests_obligation_types. Free does not mean secondary.
    is_primary_source: bool = True
    terms_url: ClassVar[str | None] = "https://data.cms.gov/about"

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the connector and its per-run metadata."""
        super().__init__(settings)
        self.distribution_title: str | None = None
        self.distribution_modified: str | None = None
        self.rows_read: int = 0

    # ----------------------------------------------------------------- fetch

    def discover_download_url(self) -> str:
        """Find the newest CSV distribution for the revalidation dataset.

        ``data.json`` lists every monthly release of this dataset as a separate
        distribution, each with its own dated path and its own ``modified``
        stamp, newest first but not guaranteed to be. The newest CSV wins.

        Returns:
            The absolute CSV URL.

        Raises:
            ConnectorError: If the dataset or a CSV distribution is not found.
        """
        catalog = self.fetch_json(DATA_JSON_URL)
        datasets = catalog.get("dataset") if isinstance(catalog, dict) else None
        if not datasets:
            raise ConnectorError(f"{DATA_JSON_URL} returned no dataset list")

        matching = [d for d in datasets if (d.get("title") or "").strip() == DATASET_TITLE]
        if not matching:
            raise ConnectorError(
                f"no dataset titled {DATASET_TITLE!r} in {DATA_JSON_URL}; CMS may have renamed it"
            )

        candidates: list[tuple[str, str, str]] = []
        for dataset in matching:
            for distribution in dataset.get("distribution", []) or []:
                url = distribution.get("downloadURL")
                if not url:
                    continue
                fmt = (distribution.get("format") or "").upper()
                media = (distribution.get("mediaType") or "").lower()
                if fmt != "CSV" and media != "text/csv" and not url.lower().endswith(".csv"):
                    continue
                candidates.append(
                    (
                        distribution.get("modified") or dataset.get("modified") or "",
                        distribution.get("title") or "",
                        url,
                    )
                )
        if not candidates:
            raise ConnectorError(f"dataset {DATASET_TITLE!r} exposes no CSV distribution")

        # Sort by the distribution's modified date, then by its title, which CMS
        # suffixes with the release date ("... : 2026-09-01"). Both are ISO-ish
        # strings, so a lexical sort is a chronological sort.
        candidates.sort(key=lambda item: (item[0], item[1]))
        modified, title, url = candidates[-1]
        self.distribution_modified = modified or None
        self.distribution_title = title or None
        self.log.info("revalidation distribution: %s (modified %s)", url, modified)
        # Refused here rather than at the first byte of a 540 MB download: this
        # URL is whatever data.json said, and data.json is a remote document.
        return self.require_allowed_url(url)

    def fetch(self) -> Path:
        """Download the newest revalidation reassignment file.

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
        url = self.discover_download_url()
        self.request_ref = url
        return self.download(
            url, self.work_file("revalidation_clinic_group_practice_reassignment.csv")
        )

    # ----------------------------------------------------------------- parse

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream normalized reassignment rows.

        Args:
            path: Local CSV.

        Yields:
            Normalized row dicts.

        Raises:
            ConnectorError: If CMS changed the header.
        """
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        self.rows_read = 0

        # encoding is latin-1 on purpose; see FILE_ENCODING.
        with path.open("r", encoding=FILE_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ConnectorError(
                    f"revalidation header changed; missing columns {missing}. "
                    f"Saw: {reader.fieldnames}"
                )
            for raw in reader:
                self.rows_read += 1
                yield {
                    "group_pac_id": _clean(raw.get(COL_GROUP_PAC_ID)) or None,
                    "group_enrollment_id": _clean(raw.get(COL_GROUP_ENROLLMENT_ID)) or None,
                    "group_legal_business_name": _clean(raw.get(COL_GROUP_LEGAL_NAME)) or None,
                    "group_state": _clean(raw.get(COL_GROUP_STATE))[:2] or None,
                    "group_due_date": _parse_due_date(raw.get(COL_GROUP_DUE_DATE)),
                    "group_reassignments": _parse_int(raw.get(COL_GROUP_REASSIGNMENTS)),
                    "record_type": _clean(raw.get(COL_RECORD_TYPE)) or None,
                    "individual_enrollment_id": _clean(raw.get(COL_IND_ENROLLMENT_ID)) or None,
                    "individual_npi": _clean(raw.get(COL_IND_NPI)) or None,
                    "individual_first_name": _clean(raw.get(COL_IND_FIRST_NAME)) or None,
                    "individual_last_name": _clean(raw.get(COL_IND_LAST_NAME)) or None,
                    "individual_state": _clean(raw.get(COL_IND_STATE))[:2] or None,
                    "individual_specialty": _clean(raw.get(COL_IND_SPECIALTY)) or None,
                    "individual_due_date": _parse_due_date(raw.get(COL_IND_DUE_DATE)),
                    "individual_total_employer_associations": _parse_int(
                        raw.get(COL_IND_TOTAL_EMPLOYER_ASSOCIATIONS)
                    ),
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """Identity of a reassignment: the individual and the group."""
        return (
            f"{row.get('individual_npi') or ''}|{row.get('group_pac_id') or ''}"
            f"|{row.get('individual_enrollment_id') or ''}"
        )

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Fields whose movement counts as a change.

        A moved due date is the whole point of this connector, so it leads.
        """
        return (
            row.get("individual_due_date"),
            row.get("group_due_date"),
            row.get("individual_total_employer_associations"),
            row.get("group_reassignments"),
            row.get("record_type"),
            row.get("group_legal_business_name"),
            row.get("group_state"),
            row.get("individual_state"),
            row.get("individual_specialty"),
        )

    # ------------------------------------------------------------------ load

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then upsert Medicare enrollments.

        Evidence is written once for the file, as with the DAC connector, and
        every derived ``enrollments`` row references it. ``enrollments`` only
        materializes for pairs whose clinician and practice already exist, which
        means the DAC connector has to have run first.

        The diff decides *whether* to load; it does not decide *what* is
        staged. ``stg_cms_revalidation`` is built from the full current file so
        that ``stg_reval_pairs`` sees every row for an (NPI, group) pair -- see
        the comment above ``_CREATE_PAIRS`` for the data loss that follows from
        staging a change set instead.

        Only the due date is written. ``status`` is set to ``approved``, the
        fact a live reassignment asserts, and never to a comparison against
        ``current_date``; the ``enrollments_current`` view derives that when it
        is read. See the note above ``_ENROLLMENT_STATUS``.

        Args:
            diff: Change set from :meth:`diff`; used to decide whether to load
                and to report ``rows_new``/``rows_changed``.
        """
        if self.fetched_path is None or self.fetched_checksum is None:
            raise ConnectorError("load() called before fetch()")

        verified_at = datetime.now(UTC)
        with transaction(None, self.settings) as conn:
            self.ensure_registered(conn)
            evidence_id = store_evidence_for_file(
                self.key,
                self.request_ref,
                self.fetched_path,
                parsed={
                    "dataset_title": DATASET_TITLE,
                    "distribution_title": self.distribution_title,
                    "distribution_modified": self.distribution_modified,
                    "rows_read": self.rows_read,
                    "encoding": FILE_ENCODING,
                    "rows_new": diff.rows_new,
                    "rows_changed": diff.rows_changed,
                },
                match_keys={
                    "individual_npi": "exact",
                    "group_pac_id": "exact",
                    "method": "bulk_file",
                },
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            if not diff.has_changes:
                self.log.info(
                    "no new or changed revalidation rows; evidence recorded, nothing derived"
                )
                return

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            # The full current file, re-parsed -- not diff.iter_rows(). See the
            # comment above _CREATE_PAIRS.
            staged = copy_from_csv(
                conn,
                "stg_cms_revalidation",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in self.parse(self.fetched_path)),
                batch_size=self.settings.copy_batch_size,
            )
            self.log.info(
                "staged %s revalidation rows (new=%s changed=%s this run)",
                f"{staged:,}",
                f"{diff.rows_new:,}",
                f"{diff.rows_changed:,}",
            )

            # enrollments.evidence_id is not-null by schema; check before the
            # writes rather than letting the constraint speak for us.
            require_evidence(conn, evidence_id)

            params = {"evidence_id": evidence_id, "verified_at": verified_at}
            with conn.cursor() as cur:
                cur.execute(_CREATE_PAIRS)
                cur.execute("create index on stg_reval_pairs (individual_npi)")
                cur.execute("create index on stg_reval_pairs (group_pac_id)")
                cur.execute("analyze stg_reval_pairs")
                cur.execute(_UPDATE_ENROLLMENTS, params)
                updated = cur.rowcount
                cur.execute(_INSERT_ENROLLMENTS, params)
                inserted = cur.rowcount
            self.log.info("medicare enrollments updated=%s inserted=%s", updated, inserted)
