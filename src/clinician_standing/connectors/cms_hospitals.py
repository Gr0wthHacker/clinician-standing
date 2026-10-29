"""CMS Hospital General Information.

About 5,400 rows, refreshed with the Care Compare releases. Every hospital
registered with Medicare: CMS Certification Number, name, address, county,
phone, hospital type, ownership, emergency services and the overall star
rating.

Its job here is to NAME the certification numbers that
``cms_facility_affiliation`` points at, so a clinician's hospital affiliations
read as hospitals rather than six-character codes. Populates ``facilities``
under ``source_key = 'cms_hospitals'`` (0016).

Small enough that the full file is staged whenever anything moved. A hospital
that leaves the file is marked ``absent_since`` -- closures and terminations
leave the file, and affiliations pointing at them are worth seeing -- and is
cleared if it returns.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import store_evidence_for_file
from ..parse import DecodeStats
from ._provider_data import discover_csv, normalize_ccn, open_csv
from .base import Connector, ConnectorError, DiffResult

__all__ = ["DATASET_ID", "CmsHospitalsConnector"]

#: Provider-data identifier for "Hospital General Information".
DATASET_ID = "xubh-q36u"

COL_CCN = "Facility ID"
COL_NAME = "Facility Name"
COL_ADDRESS = "Address"
COL_CITY = "City/Town"
COL_STATE = "State"
COL_ZIP = "ZIP Code"
COL_COUNTY = "County/Parish"
COL_PHONE = "Telephone Number"
COL_TYPE = "Hospital Type"
COL_OWNERSHIP = "Hospital Ownership"
COL_EMERGENCY = "Emergency Services"
COL_RATING = "Hospital overall rating"

REQUIRED_COLUMNS: tuple[str, ...] = (COL_CCN, COL_NAME, COL_STATE)

STAGING_COLUMNS: tuple[str, ...] = (
    "ccn",
    "name",
    "address_line1",
    "city",
    "state",
    "zip",
    "county",
    "phone",
    "facility_type",
    "ownership",
    "emergency_services",
    "overall_rating",
)

_CREATE_STAGING = """
create temporary table stg_cms_hospitals (
    ccn                text,
    name               text,
    address_line1      text,
    city               text,
    state              text,
    zip                text,
    county             text,
    phone              text,
    facility_type      text,
    ownership          text,
    emergency_services boolean,
    overall_rating     smallint
) on commit drop
"""

# A CCN another source already named is left to that source: this file speaks
# for hospitals and would otherwise overwrite, say, a nursing-home name loaded
# by a later connector under the same CCN. Hospitals' own rows are refreshed.
_UPSERT = """
insert into facilities (
    ccn, name, address_line1, city, state, zip, county, phone, facility_type,
    ownership, emergency_services, overall_rating, source_key, absent_since,
    evidence_id, updated_at
)
select distinct on (s.ccn)
    s.ccn, s.name, s.address_line1, s.city, s.state, s.zip, s.county, s.phone,
    s.facility_type, s.ownership, s.emergency_services, s.overall_rating,
    %(source_key)s, null, %(evidence_id)s, now()
from stg_cms_hospitals s
order by s.ccn, s.name
on conflict (ccn) do update set
    name               = excluded.name,
    address_line1      = excluded.address_line1,
    city               = excluded.city,
    state              = excluded.state,
    zip                = excluded.zip,
    county             = excluded.county,
    phone              = excluded.phone,
    facility_type      = excluded.facility_type,
    ownership          = excluded.ownership,
    emergency_services = excluded.emergency_services,
    overall_rating     = excluded.overall_rating,
    absent_since       = null,
    evidence_id        = excluded.evidence_id,
    updated_at         = now()
where facilities.source_key = excluded.source_key
"""

_MARK_ABSENT = """
update facilities f
   set absent_since = current_date, updated_at = now()
 where f.source_key = %(source_key)s
   and f.absent_since is null
   and not exists (select 1 from stg_cms_hospitals s where s.ccn = f.ccn)
"""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _state(value: str | None) -> str | None:
    code = _clean(value).upper()
    return code if len(code) == 2 and code.isalpha() else None


def _yes_no(value: str | None) -> bool | None:
    raw = _clean(value).lower()
    if raw in {"yes", "y", "true"}:
        return True
    if raw in {"no", "n", "false"}:
        return False
    return None


def _rating(value: str | None) -> int | None:
    """Star rating 1-5; CMS writes "Not Available" otherwise."""
    raw = _clean(value)
    return int(raw) if raw in {"1", "2", "3", "4", "5"} else None


class CmsHospitalsConnector(Connector):
    """Ingest CMS Hospital General Information into ``facilities``."""

    key: ClassVar[str] = "cms_hospitals"
    display_name: ClassVar[str] = "CMS Hospital General Information"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    freshness_sla_days: int = 45
    # A directory that names facilities; it adjudicates nothing (0016).
    is_primary_source: bool = False
    terms_url: ClassVar[str | None] = "https://data.cms.gov/provider-data/terms-of-service"
    allowed_hosts: ClassVar[frozenset[str]] = frozenset({"data.cms.gov"})

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the connector and its per-run metadata."""
        super().__init__(settings)
        self.dataset_modified: str | None = None
        self.rows_read: int = 0
        self.rows_rejected: int = 0
        self.decode_stats = DecodeStats()

    def fetch(self) -> Path:
        """Download the current Hospital General Information CSV."""
        override = self.settings.local_source_override(self.key)
        if override is not None:
            self.request_ref = f"file://{override}"
            self.fetched_is_external = True
            self.log.warning("using LOCAL_SOURCE override %s instead of fetching", override)
            return override
        entry = discover_csv(self, DATASET_ID)
        self.dataset_modified = entry.modified
        self.request_ref = entry.url
        return self.download(entry.url, self.work_file("Hospital_General_Information.csv"))

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream normalized hospital rows; rows without a valid CCN or name are dropped.

        Raises:
            ConnectorError: If a required column disappeared.
        """
        self.rows_read = 0
        self.rows_rejected = 0
        self.decode_stats = DecodeStats()
        with open_csv(path, self.decode_stats) as reader:
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ConnectorError(
                    f"hospital file header changed; missing {missing}. Saw: {reader.fieldnames}"
                )
            for raw in reader:
                self.rows_read += 1
                ccn = normalize_ccn(raw.get(COL_CCN))
                name = _clean(raw.get(COL_NAME))
                if ccn is None or not name:
                    self.rows_rejected += 1
                    continue
                yield {
                    "ccn": ccn,
                    "name": name,
                    "address_line1": _clean(raw.get(COL_ADDRESS)) or None,
                    "city": _clean(raw.get(COL_CITY)) or None,
                    "state": _state(raw.get(COL_STATE)),
                    "zip": _clean(raw.get(COL_ZIP)) or None,
                    "county": _clean(raw.get(COL_COUNTY)) or None,
                    "phone": _clean(raw.get(COL_PHONE)) or None,
                    "facility_type": _clean(raw.get(COL_TYPE)) or None,
                    "ownership": _clean(raw.get(COL_OWNERSHIP)) or None,
                    "emergency_services": _yes_no(raw.get(COL_EMERGENCY)),
                    "overall_rating": _rating(raw.get(COL_RATING)),
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """A hospital is its CCN."""
        return str(row["ccn"])

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Every loaded column except the key."""
        return tuple(row.get(c) for c in STAGING_COLUMNS if c != "ccn")

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then upsert hospitals and mark the ones that left."""
        if self.fetched_path is None or self.fetched_checksum is None:
            raise ConnectorError("load() called before fetch()")

        with transaction(None, self.settings) as conn:
            self.ensure_registered(conn)
            evidence_id = store_evidence_for_file(
                self.key,
                self.request_ref,
                self.fetched_path,
                parsed={
                    "dataset": DATASET_ID,
                    "dataset_modified": self.dataset_modified,
                    "rows_read": self.rows_read,
                    "rows_rejected": self.rows_rejected,
                    "lines_decoded_latin1": self.decode_stats.latin1_lines,
                    "rows_new": diff.rows_new,
                    "rows_changed": diff.rows_changed,
                    "rows_removed": diff.rows_removed,
                },
                match_keys={"ccn": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            if not diff.has_changes and not diff.rows_removed:
                self.log.info("no hospital rows moved; evidence recorded, nothing derived")
                return

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            staged = copy_from_csv(
                conn,
                "stg_cms_hospitals",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in self.parse(self.fetched_path)),
                batch_size=self.settings.copy_batch_size,
            )
            params = {"source_key": self.key, "evidence_id": evidence_id}
            with conn.cursor() as cur:
                cur.execute(_UPSERT, params)
                upserted = cur.rowcount
                cur.execute(_MARK_ABSENT, params)
                absent = cur.rowcount
            self.log.info(
                "hospitals staged=%s upserted=%s marked_absent=%s", staged, upserted, absent
            )
