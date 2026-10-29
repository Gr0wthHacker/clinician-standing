"""CMS Facility Affiliation Data.

Roughly 1.3M rows, refreshed monthly with the DAC file. One row per clinician
per facility they are affiliated with, by CMS Certification Number: hospitals
mostly, plus nursing homes, home health agencies, hospices, inpatient
rehabilitation facilities, long-term care hospitals and dialysis facilities.

CMS moved these affiliations out of the DAC file into this dataset, so the DAC
connector has never seen them. This is the public source of "which hospitals
does this clinician work at" that commercial provider directories sell as an
affiliation layer.

Populates ``clinician_facility_affiliations`` (0016) -- deliberately NOT
``affiliations``, which drives the obligations engine and means a billing
relationship with a client practice. A hospital privilege in a CMS directory
must never generate an obligation.

Two columns carry certification numbers:

* ``Facility Affiliations Certification Number`` -- the facility itself;
* ``Facility Type Certification Number`` -- for a unit inside a hospital (an
  inpatient rehab unit, CCN ``33T241``), the parent hospital's CCN (``330241``).
  Kept as ``parent_ccn``; ``clinician_directory`` names a unit by its parent.

Open/close semantics follow the DAC connector's affiliations exactly, and for
the same reasons: the full file is staged (closing a pair needs the whole file,
not the change set), a pair that left the file is closed only while its
clinician is still in the file (absence of a clinician is ambiguous), and
``end_date`` is the run date because CMS publishes an extract, not an event.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import store_evidence_for_file
from ..parse import DecodeStats
from ._provider_data import discover_csv, normalize_ccn, open_csv
from .base import Connector, ConnectorError, DiffResult

__all__ = ["DATASET_ID", "CmsFacilityAffiliationConnector"]

#: Provider-data identifier for "Facility Affiliation Data".
DATASET_ID = "27ea-46a8"

COL_NPI = "NPI"
COL_IND_PAC_ID = "Ind_PAC_ID"
COL_FACILITY_TYPE = "facility_type"
COL_CCN = "Facility Affiliations Certification Number"
COL_PARENT_CCN = "Facility Type Certification Number"

REQUIRED_COLUMNS: tuple[str, ...] = (COL_NPI, COL_FACILITY_TYPE, COL_CCN, COL_PARENT_CCN)

NPI_PATTERN = re.compile(r"^[0-9]{10}$")

STAGING_COLUMNS: tuple[str, ...] = ("npi", "ind_pac_id", "facility_type", "ccn", "parent_ccn")

_CREATE_STAGING = """
create temporary table stg_cfa (
    npi           text,
    ind_pac_id    text,
    facility_type text,
    ccn           text,
    parent_ccn    text
) on commit drop
"""

# One row per pair. The pair is the open-row identity in ux_cfa_open_pair, so
# collapsing here is what lets the insert below be a plain NOT EXISTS.
_CREATE_PAIRS = """
create temporary table stg_cfa_pairs on commit drop as
select distinct on (npi, facility_type, ccn, coalesce(parent_ccn, ''))
    npi, ind_pac_id, facility_type, ccn, parent_ccn
from stg_cfa
order by npi, facility_type, ccn, coalesce(parent_ccn, ''), ind_pac_id nulls last
"""

_CREATE_NPIS = """
create temporary table stg_cfa_npis on commit drop as
select distinct npi from stg_cfa
"""

_REFRESH_OPEN = """
update clinician_facility_affiliations a
   set last_seen   = current_date,
       ind_pac_id  = coalesce(s.ind_pac_id, a.ind_pac_id),
       evidence_id = %(evidence_id)s
  from stg_cfa_pairs s
 where a.end_date is null
   and a.npi = s.npi
   and a.facility_type = s.facility_type
   and a.ccn = s.ccn
   and coalesce(a.parent_ccn, '') = coalesce(s.parent_ccn, '')
"""

# NEW PAIRS ARE COMPUTED BEFORE THEY ARE INSERTED, in their own statement.
#
# The obvious `insert ... select ... where not exists (select from the same
# table)` is quadratic on a first load. The target table is empty, so its
# statistics say zero rows and the planner picks a nested-loop anti join with a
# sequential scan of the target on the inner side. The rows the INSERT writes
# are invisible to that scan (same statement, same snapshot) but they are still
# on the heap pages it reads, so every outer row rescans everything inserted so
# far. On the real 2.25M-row file that ran past nine minutes before it was
# killed. Splitting it means the anti join reads a table that is not growing
# underneath it, which costs nothing when the table is empty and is a hash anti
# join once it is not.
_CREATE_NEW_PAIRS = """
create temporary table stg_cfa_new on commit drop as
select s.npi, s.ind_pac_id, s.facility_type, s.ccn, s.parent_ccn
from stg_cfa_pairs s
where not exists (
    select 1 from clinician_facility_affiliations a
     where a.end_date is null
       and a.npi = s.npi
       and a.facility_type = s.facility_type
       and a.ccn = s.ccn
       and coalesce(a.parent_ccn, '') = coalesce(s.parent_ccn, ''))
"""

_INSERT_NEW = """
insert into clinician_facility_affiliations (
    npi, ind_pac_id, facility_type, ccn, parent_ccn, first_seen, last_seen, evidence_id
)
select npi, ind_pac_id, facility_type, ccn, parent_ccn,
       current_date, current_date, %(evidence_id)s
from stg_cfa_new
"""

# Closed only while the clinician is still in the file; see the module docstring.
_CLOSE_DEPARTED = """
update clinician_facility_affiliations a
   set end_date = current_date
 where a.end_date is null
   and exists (select 1 from stg_cfa_npis n where n.npi = a.npi)
   and not exists (
       select 1 from stg_cfa_pairs s
        where s.npi = a.npi
          and s.facility_type = a.facility_type
          and s.ccn = a.ccn
          and coalesce(s.parent_ccn, '') = coalesce(a.parent_ccn, ''))
"""


def _clean(value: str | None) -> str:
    return (value or "").strip()


class CmsFacilityAffiliationConnector(Connector):
    """Ingest CMS Facility Affiliation Data into ``clinician_facility_affiliations``."""

    key: ClassVar[str] = "cms_facility_affiliation"
    display_name: ClassVar[str] = "CMS Facility Affiliation Data"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    freshness_sla_days: int = 45
    # A directory, like the DAC file it was split from: it describes and never
    # adjudicates (0016).
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
        """Download the current Facility Affiliation CSV."""
        override = self.settings.local_source_override(self.key)
        if override is not None:
            self.request_ref = f"file://{override}"
            self.fetched_is_external = True
            self.log.warning("using LOCAL_SOURCE override %s instead of fetching", override)
            return override
        entry = discover_csv(self, DATASET_ID)
        self.dataset_modified = entry.modified
        self.request_ref = entry.url
        return self.download(entry.url, self.work_file("Facility_Affiliation.csv"))

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream normalized affiliation rows.

        Rows with a malformed NPI or certification number, or no facility type,
        are dropped and counted: each target column carries a CHECK, and one
        bad value would abort the load.

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
                    f"facility affiliation header changed; missing {missing}. "
                    f"Saw: {reader.fieldnames}"
                )
            for raw in reader:
                self.rows_read += 1
                npi = _clean(raw.get(COL_NPI))
                ccn = normalize_ccn(raw.get(COL_CCN))
                facility_type = _clean(raw.get(COL_FACILITY_TYPE))
                parent_raw = _clean(raw.get(COL_PARENT_CCN))
                parent_ccn = normalize_ccn(parent_raw) if parent_raw else None
                if (
                    not NPI_PATTERN.match(npi)
                    or ccn is None
                    or not facility_type
                    or (parent_raw and parent_ccn is None)
                ):
                    self.rows_rejected += 1
                    continue
                yield {
                    "npi": npi,
                    "ind_pac_id": _clean(raw.get(COL_IND_PAC_ID)) or None,
                    "facility_type": facility_type,
                    "ccn": ccn,
                    "parent_ccn": parent_ccn,
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """The clinician, the facility, and the facility's parent."""
        return f"{row['npi']}|{row['facility_type']}|{row['ccn']}|{row.get('parent_ccn') or ''}"

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """The only non-key column."""
        return (row.get("ind_pac_id"),)

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then open, refresh and close affiliations.

        The full current file is staged, not the change set: closing a pair
        that left the file needs to know every pair that is still in it.
        """
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
                match_keys={"npi": "exact", "ccn": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            # rows_removed matters as much as has_changes: a month whose only
            # movement is a clinician leaving a hospital has nothing new or
            # changed, and skipping the load would leave that row open forever.
            if not diff.has_changes and not diff.rows_removed:
                self.log.info("no affiliation rows moved; evidence recorded, nothing derived")
                return

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            staged = copy_from_csv(
                conn,
                "stg_cfa",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in self.parse(self.fetched_path)),
                batch_size=self.settings.copy_batch_size,
            )
            params = {"evidence_id": evidence_id}
            with conn.cursor() as cur:
                cur.execute(_CREATE_PAIRS)
                cur.execute("create index on stg_cfa_pairs (npi, facility_type, ccn)")
                cur.execute(_CREATE_NPIS)
                cur.execute("create index on stg_cfa_npis (npi)")
                cur.execute("analyze stg_cfa_pairs")
                cur.execute("analyze stg_cfa_npis")
                cur.execute(_REFRESH_OPEN, params)
                refreshed = cur.rowcount
                cur.execute(_CREATE_NEW_PAIRS)
                cur.execute(_INSERT_NEW, params)
                inserted = cur.rowcount
                cur.execute(_CLOSE_DEPARTED)
                closed = cur.rowcount
            self.log.info(
                "facility affiliations staged=%s refreshed=%s inserted=%s closed=%s",
                f"{staged:,}",
                f"{refreshed:,}",
                f"{inserted:,}",
                f"{closed:,}",
            )
