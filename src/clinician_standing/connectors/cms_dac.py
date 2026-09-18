"""CMS Doctors and Clinicians National Downloadable File (the "DAC" file).

Roughly 839 MB and 3.39M lines, refreshed monthly. It is the identity spine of
the whole system: it carries NPI, the individual PAC ID and enrollment ID, the
group PAC ID that every other CMS file joins on, credential, primary specialty,
practice name, address and phone.

Two things about this file decide whether downstream numbers are right:

1. **One line per clinician per practice location.** CMS states it plainly in
   the dataset description: "Clinicians with multiple Medicare enrollment
   records and/or single enrollments linking to multiple practice locations are
   listed on multiple lines." Deduplicating on ``(NPI, org_pac_id)`` before any
   count or load is not an optimization, it is the difference between a correct
   roster and a roster that triple-counts multi-site physicians.
2. **The download URL changes every month.** It carries a content hash and a
   version stamp, so it is discovered from the metastore item rather than
   hardcoded.

Populates ``practices``, ``clinicians`` and ``affiliations``.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import store_evidence_for_file
from .base import Connector, ConnectorError, DiffResult

__all__ = ["METADATA_URL", "CmsDacConnector"]

#: Metastore item for dataset mj5m-pzi6, "National Downloadable File".
METADATA_URL = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/mj5m-pzi6"

#: Header names exactly as CMS publishes them. Mixed case and spacing are CMS's,
#: not ours; do not normalize them here or the DictReader lookups break.
COL_NPI = "NPI"
COL_IND_PAC_ID = "Ind_PAC_ID"
COL_IND_ENRL_ID = "Ind_enrl_ID"
COL_LAST_NAME = "Provider Last Name"
COL_FIRST_NAME = "Provider First Name"
COL_MIDDLE_NAME = "Provider Middle Name"
COL_SUFFIX = "suff"
COL_CRED = "Cred"
COL_PRI_SPEC = "pri_spec"
COL_TELEHEALTH = "Telehlth"
COL_FACILITY_NAME = "Facility Name"
COL_ORG_PAC_ID = "org_pac_id"
COL_NUM_ORG_MEM = "num_org_mem"
COL_ADR_LN_1 = "adr_ln_1"
COL_ADR_LN_2 = "adr_ln_2"
COL_CITY = "City/Town"
COL_STATE = "State"
COL_ZIP = "ZIP Code"
COL_PHONE = "Telephone Number"

REQUIRED_COLUMNS: tuple[str, ...] = (
    COL_NPI,
    COL_IND_PAC_ID,
    COL_IND_ENRL_ID,
    COL_CRED,
    COL_PRI_SPEC,
    COL_TELEHEALTH,
    COL_FACILITY_NAME,
    COL_ORG_PAC_ID,
    COL_NUM_ORG_MEM,
    COL_ADR_LN_1,
    COL_ADR_LN_2,
    COL_CITY,
    COL_STATE,
    COL_ZIP,
    COL_PHONE,
)

#: ``Cred`` value -> ``clinicians.clinician_type``. Everything unmapped becomes
#: ``other``; the file carries dozens of allied-health credentials (PT, OT, CSW,
#: DC, OD, AU, DPM ...) that this product does not treat as prescribers.
CREDENTIAL_TO_TYPE: dict[str, str] = {
    "MD": "physician",
    "DO": "physician",
    "NP": "np",
    "PA": "pa",
    "CRNA": "crna",
}

#: Specialty fallback when ``Cred`` is blank, which happens on ~16% of lines.
SPECIALTY_TO_TYPE: dict[str, str] = {
    "NURSE PRACTITIONER": "np",
    "PHYSICIAN ASSISTANT": "pa",
    "CERTIFIED REGISTERED NURSE ANESTHETIST (CRNA)": "crna",
    "ANESTHESIOLOGY ASSISTANT": "other",
}

STAGING_COLUMNS: tuple[str, ...] = (
    "npi",
    "ind_pac_id",
    "ind_enrl_id",
    "first_name",
    "last_name",
    "middle_name",
    "suffix",
    "credential",
    "clinician_type",
    "primary_specialty",
    "telehealth",
    "facility_name",
    "org_pac_id",
    "num_org_mem",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "zip",
    "phone",
)

_CREATE_STAGING = """
create temporary table stg_cms_dac (
    npi               text,
    ind_pac_id        text,
    ind_enrl_id       text,
    first_name        text,
    last_name         text,
    middle_name       text,
    suffix            text,
    credential        text,
    clinician_type    text,
    primary_specialty text,
    telehealth        boolean,
    facility_name     text,
    org_pac_id        text,
    num_org_mem       integer,
    address_line1     text,
    address_line2     text,
    city              text,
    state             text,
    zip               text,
    phone             text
) on commit drop
"""

# Only CMS-derived demographics are refreshed on conflict. client_status, tier,
# size_discount and onboarded_at are owned by delivery, not by an ingest job.
_UPSERT_PRACTICES = """
insert into practices (
    id, org_pac_id, legal_name, address_line1, address_line2, city, state, zip, phone
)
select distinct on (s.org_pac_id)
    gen_random_uuid(), s.org_pac_id, s.facility_name, s.address_line1, s.address_line2,
    s.city, left(s.state, 2), s.zip, s.phone
from stg_cms_dac s
where s.org_pac_id is not null
  and s.org_pac_id <> ''
  and s.facility_name is not null
  and s.facility_name <> ''
order by s.org_pac_id, s.num_org_mem desc nulls last
on conflict (org_pac_id) do update set
    legal_name    = excluded.legal_name,
    address_line1 = excluded.address_line1,
    address_line2 = excluded.address_line2,
    city          = excluded.city,
    state         = excluded.state,
    zip           = excluded.zip,
    phone         = excluded.phone
"""

_UPSERT_CLINICIANS = """
insert into clinicians (
    id, npi, ind_pac_id, ind_enrl_id, first_name, last_name, middle_name, suffix,
    credential, clinician_type, primary_specialty
)
select distinct on (s.npi)
    gen_random_uuid(), s.npi, s.ind_pac_id, s.ind_enrl_id, s.first_name, s.last_name,
    s.middle_name, s.suffix, nullif(s.credential, ''), s.clinician_type,
    nullif(s.primary_specialty, '')
from stg_cms_dac s
where s.npi is not null and s.npi <> ''
order by s.npi, s.num_org_mem desc nulls last
on conflict (npi) do update set
    ind_pac_id        = coalesce(excluded.ind_pac_id, clinicians.ind_pac_id),
    ind_enrl_id       = coalesce(excluded.ind_enrl_id, clinicians.ind_enrl_id),
    first_name        = coalesce(excluded.first_name, clinicians.first_name),
    last_name         = coalesce(excluded.last_name, clinicians.last_name),
    middle_name       = coalesce(excluded.middle_name, clinicians.middle_name),
    suffix            = coalesce(excluded.suffix, clinicians.suffix),
    credential        = coalesce(excluded.credential, clinicians.credential),
    clinician_type    = excluded.clinician_type,
    primary_specialty = coalesce(excluded.primary_specialty, clinicians.primary_specialty)
"""

# The DAC file carries no start date, so affiliations.start_date stays null and
# the natural unique key (clinician_id, practice_id, start_date) cannot be used
# as a conflict target: in SQL, null never conflicts with null. An explicit
# NOT EXISTS on the open affiliation is the guard instead.
_INSERT_AFFILIATIONS = """
insert into affiliations (id, clinician_id, practice_id, is_billing)
select gen_random_uuid(), c.id, p.id, true
from (
    select distinct npi, org_pac_id
    from stg_cms_dac
    where npi <> '' and org_pac_id is not null and org_pac_id <> ''
) s
join clinicians c on c.npi = s.npi
join practices  p on p.org_pac_id = s.org_pac_id
where not exists (
    select 1 from affiliations a
    where a.clinician_id = c.id and a.practice_id = p.id and a.end_date is null
)
"""


#: clinicians.npi carries a CHECK for exactly ten digits. A single malformed
#: value would abort a two-million-row transaction, so parse drops it instead.
NPI_PATTERN = re.compile(r"^[0-9]{10}$")

#: practices.state carries a CHECK for two uppercase letters.
STATE_PATTERN = re.compile(r"^[A-Z]{2}$")


def _clean(value: str | None) -> str:
    """Trim a CSV field, mapping None to empty string."""
    return (value or "").strip()


def _state(value: str | None) -> str | None:
    """Normalize a state code to two uppercase letters, or None."""
    code = _clean(value).upper()[:2]
    return code if STATE_PATTERN.match(code) else None


def _clinician_type(credential: str, specialty: str) -> str:
    """Map CMS credential/specialty onto ``clinicians.clinician_type``."""
    mapped = CREDENTIAL_TO_TYPE.get(credential.upper())
    if mapped:
        return mapped
    return SPECIALTY_TO_TYPE.get(specialty.upper(), "other")


class CmsDacConnector(Connector):
    """Ingest the CMS Doctors and Clinicians National Downloadable File."""

    key: ClassVar[str] = "cms_dac"
    display_name: ClassVar[str] = "CMS Doctors and Clinicians National Downloadable File"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    # Published monthly with a stated next-update date; 45 days allows one late
    # publication before dependent assertions go stale.
    freshness_sla_days: ClassVar[int] = 45
    # The registry (db/migrations/0009_seed_sources.sql) seeds this source with
    # is_primary_source = false: PRD 5.5 says false means it cannot alone clear
    # an obligation, and a federal bulk file is a directory extract, not a
    # primary-source verification. The class attribute matches the seed so a
    # fresh database and a seeded one behave identically.
    is_primary_source: ClassVar[bool] = False
    terms_url: ClassVar[str | None] = "https://data.cms.gov/provider-data/terms-of-service"

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the connector and its per-run metadata."""
        super().__init__(settings)
        self.dataset_modified: str | None = None
        self.distribution_version: str | None = None
        self.rows_before_dedupe: int = 0
        self.rows_rejected: int = 0

    # ----------------------------------------------------------------- fetch

    def discover_download_url(self) -> str:
        """Resolve the current CSV URL from the CMS metastore item.

        The published URL looks like
        ``.../resources/<md5>_<version>/DAC_NationalDownloadableFile.csv``. Both
        the hash and the version change with each monthly release, so hardcoding
        it guarantees a stale or 404 fetch within a month.

        Returns:
            The absolute CSV URL.

        Raises:
            ConnectorError: If the metastore item exposes no CSV distribution.
        """
        document = self.fetch_json(METADATA_URL)
        if not isinstance(document, dict):
            raise ConnectorError(f"{METADATA_URL} did not return a dataset object")
        self.dataset_modified = document.get("modified")

        for distribution in document.get("distribution", []) or []:
            data = distribution.get("data") or {}
            media_type = (data.get("mediaType") or "").lower()
            url = data.get("downloadURL")
            if url and (media_type == "text/csv" or url.lower().endswith(".csv")):
                refs = data.get("%Ref:downloadURL") or []
                if refs:
                    self.distribution_version = (refs[0].get("data") or {}).get("version")
                self.log.info(
                    "DAC distribution: %s (dataset modified %s)", url, self.dataset_modified
                )
                return url
        raise ConnectorError(f"no CSV distribution found in the metastore item at {METADATA_URL}")

    def fetch(self) -> Path:
        """Download the current national downloadable file.

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
        return self.download(url, self.work_file("DAC_NationalDownloadableFile.csv"))

    # ----------------------------------------------------------------- parse

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream deduplicated rows out of the DAC file.

        Deduplication happens here, on ``(NPI, org_pac_id)``, so that every
        count, diff and load downstream sees one row per clinician per practice
        rather than one per practice *location*. A physician at a four-site group
        appears on four lines with the same ``org_pac_id`` and four different
        ``adrs_id`` values; without this the roster and every derived metric
        inflate.

        Args:
            path: Local CSV.

        Yields:
            Normalized row dicts.

        Raises:
            ConnectorError: If CMS changed the header and a required column
                disappeared. Failing loudly beats loading nulls.
        """
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        seen: set[int] = set()
        self.rows_before_dedupe = 0
        self.rows_rejected = 0

        # The file is UTF-8 with a byte-order mark; utf-8-sig strips it so the
        # first header name is "NPI" and not "﻿NPI".
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ConnectorError(
                    f"DAC header changed; missing columns {missing}. Saw: {reader.fieldnames}"
                )
            for raw in reader:
                self.rows_before_dedupe += 1
                npi = _clean(raw.get(COL_NPI))
                if not NPI_PATTERN.match(npi):
                    if npi:
                        self.rows_rejected += 1
                    continue
                org_pac_id = _clean(raw.get(COL_ORG_PAC_ID))

                dedupe_key = f"{npi}|{org_pac_id}"
                digest = int.from_bytes(
                    hashlib.blake2b(dedupe_key.encode("utf-8"), digest_size=8).digest(), "big"
                )
                if digest in seen:
                    continue
                seen.add(digest)

                credential = _clean(raw.get(COL_CRED))
                specialty = _clean(raw.get(COL_PRI_SPEC))
                num_org_mem = _clean(raw.get(COL_NUM_ORG_MEM))
                yield {
                    "npi": npi,
                    "ind_pac_id": _clean(raw.get(COL_IND_PAC_ID)) or None,
                    "ind_enrl_id": _clean(raw.get(COL_IND_ENRL_ID)) or None,
                    "first_name": _clean(raw.get(COL_FIRST_NAME)) or None,
                    "last_name": _clean(raw.get(COL_LAST_NAME)) or None,
                    "middle_name": _clean(raw.get(COL_MIDDLE_NAME)) or None,
                    "suffix": _clean(raw.get(COL_SUFFIX)) or None,
                    "credential": credential,
                    "clinician_type": _clinician_type(credential, specialty),
                    "primary_specialty": specialty,
                    # Telehlth is "Y" or empty; CMS publishes no explicit "N".
                    "telehealth": _clean(raw.get(COL_TELEHEALTH)).upper() == "Y",
                    "facility_name": _clean(raw.get(COL_FACILITY_NAME)),
                    "org_pac_id": org_pac_id or None,
                    "num_org_mem": int(num_org_mem) if num_org_mem.isdigit() else None,
                    "address_line1": _clean(raw.get(COL_ADR_LN_1)) or None,
                    "address_line2": _clean(raw.get(COL_ADR_LN_2)) or None,
                    "city": _clean(raw.get(COL_CITY)) or None,
                    "state": _state(raw.get(COL_STATE)),
                    "zip": _clean(raw.get(COL_ZIP)) or None,
                    "phone": _clean(raw.get(COL_PHONE)) or None,
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """Identity of a DAC row: the clinician and the group they bill under."""
        return f"{row['npi']}|{row.get('org_pac_id') or ''}"

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Fields whose movement counts as a change worth reloading."""
        return (
            row.get("ind_pac_id"),
            row.get("ind_enrl_id"),
            row.get("first_name"),
            row.get("last_name"),
            row.get("middle_name"),
            row.get("suffix"),
            row.get("credential"),
            row.get("clinician_type"),
            row.get("primary_specialty"),
            row.get("telehealth"),
            row.get("facility_name"),
            row.get("num_org_mem"),
            row.get("address_line1"),
            row.get("address_line2"),
            row.get("city"),
            row.get("state"),
            row.get("zip"),
            row.get("phone"),
        )

    # ------------------------------------------------------------------ load

    def load(self, diff: DiffResult) -> None:
        """Write evidence, then derive practices, clinicians and affiliations.

        Evidence is written for the file as a whole. The DAC file *is* the
        primary-source snapshot, and one evidence row per clinician-practice
        pair would mean 3.39M evidence rows a month against a schema sized for
        ~50k. ``match_keys`` records which identity keys this evidence can be
        joined on, which is what section 8.1 checks.

        Args:
            diff: Change set from :meth:`diff`.
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
                    "dataset": "mj5m-pzi6",
                    "dataset_modified": self.dataset_modified,
                    "distribution_version": self.distribution_version,
                    "lines_read": self.rows_before_dedupe,
                    "rows_rejected_bad_npi": self.rows_rejected,
                    "rows_after_dedupe": diff.rows_in,
                    "dedupe_key": ["NPI", "org_pac_id"],
                    "rows_new": diff.rows_new,
                    "rows_changed": diff.rows_changed,
                },
                match_keys={"npi": "exact", "org_pac_id": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            if not diff.has_changes:
                self.log.info("no new or changed DAC rows; evidence recorded, nothing derived")
                return

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)

            staged = copy_from_csv(
                conn,
                "stg_cms_dac",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in diff.iter_rows()),
                batch_size=self.settings.copy_batch_size,
            )
            self.log.info("staged %s changed DAC rows", f"{staged:,}")

            with conn.cursor() as cur:
                cur.execute("create index on stg_cms_dac (npi)")
                cur.execute("create index on stg_cms_dac (org_pac_id)")
                cur.execute("analyze stg_cms_dac")
                cur.execute(_UPSERT_PRACTICES)
                practices = cur.rowcount
                cur.execute(_UPSERT_CLINICIANS)
                clinicians = cur.rowcount
                cur.execute(_INSERT_AFFILIATIONS)
                affiliations = cur.rowcount
            self.log.info(
                "practices upserted=%s clinicians upserted=%s affiliations inserted=%s",
                practices,
                clinicians,
                affiliations,
            )
