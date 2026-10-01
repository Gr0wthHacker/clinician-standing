"""NPPES full replicate (the monthly "NPPES Data Dissemination" file).

About 1.2 GB zipped and 11.7 GB unzipped (September 2026), one row per NPI
ever issued (~9M), refreshed monthly. It is the national directory every
commercial provider-data product starts from: entity type, legal and
organization names, credential text, practice location, up to fifteen taxonomy slots each with a self-reported
license number and state, the authorized official for organizations, and
deactivation and reactivation dates.

Populates ``nppes_providers`` (0016). It does not write the roster:
``clinicians`` comes from the DAC file, and ``clinician_directory`` joins the
two on NPI at read time.

Things about this file that decide whether the load is right:

* **The URL is on a web page, not in a catalog.** The current file is linked
  from ``download.cms.gov/nppes/NPI_Files.html`` with the month in its name
  (``NPPES_Data_Dissemination_September_2026_V2.zip``). It is discovered from
  that page, V.2 format preferred; the link read out of the page is checked
  against the download allowlist like any catalog URL.
* **Encoding is not stated.** The readme is silent and the file is too large to
  probe usefully, so lines are decoded UTF-8 with a per-line latin-1 fallback
  (:func:`clinician_standing.parse.decode_lines`). Never lossy, never raises.
* **Deactivated NPIs are stubs.** CMS publishes only the NPI and deactivation
  date for them, every other column blank. Loading a stub over an existing row
  would erase the provider's name and taxonomy, so the upsert keeps the stored
  descriptive columns when the incoming row is a stub and takes only the status
  columns from it.
* **It never streams to disk unzipped.** The CSV member is read straight out of
  the zip, twice for the diff and once more for a full stage when one is needed.
  The diff's spill file on a first run is the whole directory (several GB); see
  the disk note in ``ingest-monthly.yml``.
* **EIN and parent-organization TIN are not loaded.** A sole proprietor's TIN
  can be an SSN, and nothing in this product needs either (CONTRIBUTING.md:
  provider data only, and only what is used).

The weekly incremental files and the monthly deactivation file are not read
here. The monthly replicate is complete on its own; the weekly files would only
narrow the freshness window, and can be added as a second connector writing the
same table.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.parse
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import IO, Any, ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import store_evidence_for_file
from ..parse import DecodeStats, decode_lines
from .base import Connector, ConnectorError, DiffResult

__all__ = ["INDEX_URL", "NppesConnector", "find_replicate_link", "normalize_header"]

#: The page CMS links every NPPES download from.
INDEX_URL = "https://download.cms.gov/nppes/NPI_Files.html"

#: The monthly replicate link, V.2 format. Month name and year are in the file
#: name; anything else in the name (the weekly files carry dates, the
#: deactivation report says so) is a different file.
_V2_LINK = re.compile(
    r"""href\s*=\s*["']([^"']*NPPES_Data_Dissemination_[A-Za-z]+_\d{4}_V2\.zip)["']""",
    re.IGNORECASE,
)
#: V.1 fallback, for the month CMS stops publishing V.2 or before it started.
_V1_LINK = re.compile(
    r"""href\s*=\s*["']([^"']*NPPES_Data_Dissemination_[A-Za-z]+_\d{4}\.zip)["']""",
    re.IGNORECASE,
)

#: The data member inside the zip. The zip also carries a ``_fileheader.csv``,
#: the practice-location, other-name and endpoint files, and a PDF.
_MEMBER = re.compile(r"(^|/)npidata_pfile_\d{8}-\d{8}\.csv$", re.IGNORECASE)

#: NPPES dates are MM/DD/YYYY.
DATE_FORMAT = "%m/%d/%Y"

NPI_PATTERN = re.compile(r"^[0-9]{10}$")

#: Taxonomy slot columns carry a ``_N`` suffix, 1-15.
_SLOT = re.compile(r"^(.*?)(\d+)$")


def normalize_header(name: str) -> str:
    """Lowercase a header and drop everything but letters and digits.

    NPPES headers are long and punctuated ("Provider Business Practice Location
    Address Country Code (If outside U.S.)"). Matching on the normalized form
    tolerates the spacing, punctuation and casing drift a format revision
    brings, while still failing loudly when a field genuinely disappears.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


#: Logical field -> published header. Matched through :func:`normalize_header`.
FIELDS: dict[str, str] = {
    "npi": "NPI",
    "entity_type": "Entity Type Code",
    "replacement_npi": "Replacement NPI",
    "organization_name": "Provider Organization Name (Legal Business Name)",
    "other_organization_name": "Provider Other Organization Name",
    "last_name": "Provider Last Name (Legal Name)",
    "first_name": "Provider First Name",
    "middle_name": "Provider Middle Name",
    "name_prefix": "Provider Name Prefix Text",
    "name_suffix": "Provider Name Suffix Text",
    "credential": "Provider Credential Text",
    "practice_address_line1": "Provider First Line Business Practice Location Address",
    "practice_address_line2": "Provider Second Line Business Practice Location Address",
    "practice_city": "Provider Business Practice Location Address City Name",
    "practice_state": "Provider Business Practice Location Address State Name",
    "practice_postal_code": "Provider Business Practice Location Address Postal Code",
    "practice_country_code": (
        "Provider Business Practice Location Address Country Code (If outside U.S.)"
    ),
    "practice_phone": "Provider Business Practice Location Address Telephone Number",
    "enumeration_date": "Provider Enumeration Date",
    "last_update_date": "Last Update Date",
    "certification_date": "Certification Date",
    "deactivation_reason_code": "NPI Deactivation Reason Code",
    "deactivation_date": "NPI Deactivation Date",
    "reactivation_date": "NPI Reactivation Date",
    "is_sole_proprietor": "Is Sole Proprietor",
    "is_organization_subpart": "Is Organization Subpart",
    "parent_organization_lbn": "Parent Organization LBN",
    "authorized_official_last_name": "Authorized Official Last Name",
    "authorized_official_first_name": "Authorized Official First Name",
    "authorized_official_middle_name": "Authorized Official Middle Name",
    "authorized_official_title": "Authorized Official Title or Position",
    "authorized_official_phone": "Authorized Official Telephone Number",
}

#: Without these the file is not the file we think it is.
REQUIRED_FIELDS: tuple[str, ...] = (
    "npi",
    "entity_type",
    "last_update_date",
    "deactivation_date",
)

#: Taxonomy slot prefixes (normalized), slot number appended in the file.
_SLOT_FIELDS: dict[str, str] = {
    normalize_header("Healthcare Provider Taxonomy Code_"): "code",
    normalize_header("Provider License Number_"): "license_number",
    normalize_header("Provider License Number State Code_"): "license_state",
    normalize_header("Healthcare Provider Primary Taxonomy Switch_"): "primary",
    normalize_header("Healthcare Provider Taxonomy Group_"): "group",
}

#: Columns written to ``nppes_providers`` from a parsed row, in staging order.
STAGING_COLUMNS: tuple[str, ...] = (*FIELDS.keys(), "primary_taxonomy_code", "taxonomies")

#: Columns that describe the provider and are blank on a deactivation stub.
#: On a stub the stored value is kept; see the module docstring.
DESCRIPTIVE_COLUMNS: tuple[str, ...] = (
    "entity_type",
    "organization_name",
    "other_organization_name",
    "last_name",
    "first_name",
    "middle_name",
    "name_prefix",
    "name_suffix",
    "credential",
    "practice_address_line1",
    "practice_address_line2",
    "practice_city",
    "practice_state",
    "practice_postal_code",
    "practice_country_code",
    "practice_phone",
    "enumeration_date",
    "certification_date",
    "is_sole_proprietor",
    "is_organization_subpart",
    "parent_organization_lbn",
    "authorized_official_last_name",
    "authorized_official_first_name",
    "authorized_official_middle_name",
    "authorized_official_title",
    "authorized_official_phone",
    "primary_taxonomy_code",
    "taxonomies",
)

#: Columns a stub does speak to: always taken from the incoming row.
STATUS_COLUMNS: tuple[str, ...] = tuple(
    c for c in STAGING_COLUMNS if c not in DESCRIPTIVE_COLUMNS and c != "npi"
)

_STAGING_TYPES: dict[str, str] = {
    "entity_type": "smallint",
    "enumeration_date": "date",
    "last_update_date": "date",
    "certification_date": "date",
    "deactivation_date": "date",
    "reactivation_date": "date",
    "is_sole_proprietor": "boolean",
    "is_organization_subpart": "boolean",
}

_CREATE_STAGING = (
    "create temporary table stg_nppes (\n    "
    + ",\n    ".join(f"{c} {_STAGING_TYPES.get(c, 'text')}" for c in STAGING_COLUMNS)
    + "\n) on commit drop"
)


def _upsert_sql() -> str:
    """Build the upsert from the column lists, so the three never drift apart.

    ``distinct on (npi) ... order by last_update_date desc`` guards a repeated
    NPI in the change set: ``on conflict do update`` refuses to touch one row
    twice in a statement, and NPPES has never promised uniqueness in writing.
    """
    insert_cols = [*STAGING_COLUMNS, "absent_since", "evidence_id", "updated_at"]
    select_cols = [
        "s.taxonomies::jsonb" if c == "taxonomies" else f"s.{c}" for c in STAGING_COLUMNS
    ]
    select_cols += ["null", "%(evidence_id)s", "now()"]
    # A stub is a row with no entity type: NPPES blanks every descriptive column
    # on a deactivated NPI, including that one.
    updates = [
        f"{c} = case when excluded.entity_type is null "
        f"then nppes_providers.{c} else excluded.{c} end"
        for c in DESCRIPTIVE_COLUMNS
    ]
    updates += [f"{c} = excluded.{c}" for c in STATUS_COLUMNS]
    updates += [
        "absent_since = null",
        "evidence_id = excluded.evidence_id",
        "updated_at = now()",
    ]
    return (
        f"insert into nppes_providers ({', '.join(insert_cols)})\n"
        f"select distinct on (s.npi) {', '.join(select_cols)}\n"
        "from stg_nppes s\n"
        "order by s.npi, s.last_update_date desc nulls last\n"
        "on conflict (npi) do update set\n    " + ",\n    ".join(updates)
    )


_UPSERT = _upsert_sql()

_CREATE_PRESENT = "create temporary table stg_nppes_present (npi text) on commit drop"

# Only reached when the diff reports keys that vanished. NPPES does not delete
# NPIs, so this marks rather than deletes, and a returning NPI is cleared by
# _UPSERT. current_date, not the file date: the honest claim is "not in the
# file as of this run".
_MARK_ABSENT = """
update nppes_providers p
   set absent_since = current_date, updated_at = now()
 where p.absent_since is null
   and not exists (select 1 from stg_nppes_present s where s.npi = p.npi)
"""


def _clean(value: str | None) -> str:
    """Trim a field. NPPES encloses every value in quotes; csv strips those."""
    return (value or "").strip()


def _at(raw: Sequence[str], index: int | None) -> str:
    """The trimmed cell at ``index``, or empty when the column or cell is absent.

    A short row (a truncated last line, a stub with trailing columns omitted)
    reads as blanks rather than raising IndexError mid-file.
    """
    return _clean(raw[index]) if index is not None and index < len(raw) else ""


def _date(value: str | None) -> date | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, DATE_FORMAT).date()
    except ValueError:
        return None


def _flag(value: str | None) -> bool | None:
    """``Y``/``N`` to a bool. NPPES writes ``X`` for "not answered": None."""
    raw = _clean(value).upper()
    if raw == "Y":
        return True
    if raw == "N":
        return False
    return None


def _npi_or_none(value: str | None) -> str | None:
    raw = _clean(value)
    return raw if NPI_PATTERN.match(raw) else None


def find_replicate_link(page: str, page_url: str = INDEX_URL) -> str | None:
    """Find the monthly replicate's URL on the NPPES downloads page.

    V.2 is preferred; V.1 is the fallback. Relative links are resolved against
    ``page_url``. CMS lists the current monthly file once; if a page ever lists
    two, the first (topmost) link wins, which is where CMS puts the current one.

    Args:
        page: HTML of the downloads page.
        page_url: The page's own URL, for resolving relative links.

    Returns:
        The absolute URL, or None when no replicate link is present.
    """
    for pattern in (_V2_LINK, _V1_LINK):
        links = pattern.findall(page)
        if links:
            return urllib.parse.urljoin(page_url, str(links[0]))
    return None


class NppesConnector(Connector):
    """Ingest the NPPES full replicate into ``nppes_providers``."""

    key: ClassVar[str] = "nppes"
    display_name: ClassVar[str] = "NPPES NPI Registry Full Replicate"
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    freshness_sla_days: int = 45
    # The registry is authoritative (0009/0010 seed it primary, attesting to
    # directory_attestation only). ensure_registered() adopts the stored value.
    is_primary_source: bool = True
    terms_url: ClassVar[str | None] = INDEX_URL
    allowed_hosts: ClassVar[frozenset[str]] = frozenset({"download.cms.gov"})

    def __init__(self, settings: Any | None = None) -> None:
        """Initialize the connector and its per-run metadata."""
        super().__init__(settings)
        self.member_name: str | None = None
        self.rows_read: int = 0
        self.rows_rejected: int = 0
        self.deactivated_stubs: int = 0
        self.taxonomy_slots: int = 0
        self.decode_stats = DecodeStats()
        self.missing_optional_fields: list[str] = []

    # ----------------------------------------------------------------- fetch

    def discover_download_url(self) -> str:
        """Read the current replicate link off the NPPES downloads page.

        Returns:
            The absolute zip URL, already checked against the allowlist.

        Raises:
            ConnectorError: When the page carries no replicate link.
        """
        page = self.fetch_text(INDEX_URL)
        url = find_replicate_link(page)
        if url is None:
            raise ConnectorError(
                f"no NPPES_Data_Dissemination_<Month>_<Year>[_V2].zip link on {INDEX_URL}; "
                "CMS may have renamed the file"
            )
        self.log.info("NPPES replicate: %s", url)
        return self.require_allowed_url(url)

    def fetch(self) -> Path:
        """Download the current replicate zip.

        ``LOCAL_SOURCE_NPPES`` may name the zip or an already-extracted
        ``npidata_pfile_*.csv``.

        Returns:
            Path to the local zip or CSV.
        """
        override = self.settings.local_source_override(self.key)
        if override is not None:
            self.request_ref = f"file://{override}"
            self.fetched_is_external = True
            self.log.warning("using LOCAL_SOURCE override %s instead of fetching", override)
            return override
        url = self.discover_download_url()
        self.request_ref = url
        return self.download(url, self.work_file(Path(urllib.parse.urlsplit(url).path).name))

    # ----------------------------------------------------------------- parse

    @contextmanager
    def _open_binary(self, path: Path) -> Iterator[IO[bytes]]:
        """Open the data member of the zip, or the CSV itself, as bytes."""
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                members = [n for n in archive.namelist() if _MEMBER.search(n)]
                if len(members) != 1:
                    raise ConnectorError(
                        f"expected exactly one npidata_pfile_<from>-<to>.csv in {path.name}, "
                        f"found {members or 'none'}"
                    )
                self.member_name = members[0]
                with archive.open(members[0]) as member:
                    yield member
        else:
            self.member_name = path.name
            with path.open("rb") as handle:
                yield handle

    def _resolve_header(
        self, header: Sequence[str]
    ) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
        """Map logical fields and taxonomy slots to column positions.

        Raises:
            ConnectorError: If a required field or the first taxonomy slot is
                missing. Optional fields that are missing are recorded and
                logged, and load as null.
        """
        positions = {normalize_header(name): i for i, name in enumerate(header)}
        fields: dict[str, int] = {}
        missing_required: list[str] = []
        self.missing_optional_fields = []
        for logical, published in FIELDS.items():
            index = positions.get(normalize_header(published))
            if index is not None:
                fields[logical] = index
            elif logical in REQUIRED_FIELDS:
                missing_required.append(published)
            else:
                self.missing_optional_fields.append(published)

        slots: dict[int, dict[str, int]] = {}
        for name, index in positions.items():
            match = _SLOT.match(name)
            if not match or match.group(1) not in _SLOT_FIELDS:
                continue
            slots.setdefault(int(match.group(2)), {})[_SLOT_FIELDS[match.group(1)]] = index
        if 1 not in slots or "code" not in slots[1]:
            missing_required.append("Healthcare Provider Taxonomy Code_1")

        if missing_required:
            raise ConnectorError(
                f"NPPES header changed; missing {missing_required}. First columns seen: "
                f"{list(header)[:12]}"
            )
        if self.missing_optional_fields:
            self.log.warning(
                "NPPES header no longer carries %s; those columns load as null",
                self.missing_optional_fields,
            )
        self.taxonomy_slots = len(slots)
        return fields, dict(sorted(slots.items()))

    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream normalized NPPES rows.

        Args:
            path: The replicate zip, or the extracted data CSV.

        Yields:
            One row per NPI, ready for staging. ``taxonomies`` is a JSON string
            so that the diff's content hash and the staging COPY both see one
            stable value.

        Raises:
            ConnectorError: On a missing data member or a changed header.
        """
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        self.rows_read = 0
        self.rows_rejected = 0
        self.deactivated_stubs = 0
        self.decode_stats = DecodeStats()

        with self._open_binary(path) as binary:
            reader = csv.reader(decode_lines(binary, self.decode_stats))
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ConnectorError(f"{path.name}: empty NPPES data file") from exc
            fields, slots = self._resolve_header(header)

            def cell(raw: list[str], logical: str) -> str:
                return _at(raw, fields.get(logical))

            for raw in reader:
                self.rows_read += 1
                npi = cell(raw, "npi")
                if not NPI_PATTERN.match(npi):
                    self.rows_rejected += 1
                    continue

                taxonomies: list[dict[str, Any]] = []
                for slot, columns in slots.items():
                    code = _at(raw, columns.get("code"))
                    if not code:
                        continue
                    taxonomies.append(
                        {
                            "slot": slot,
                            "code": code,
                            "license_number": _at(raw, columns.get("license_number")) or None,
                            "license_state": _at(raw, columns.get("license_state")).upper() or None,
                            "primary": _at(raw, columns.get("primary")).upper() == "Y",
                            "group": _at(raw, columns.get("group")) or None,
                        }
                    )
                primaries = [t["code"] for t in taxonomies if t["primary"]]
                if primaries:
                    primary_code: str | None = primaries[0]
                elif len(taxonomies) == 1:
                    # A single taxonomy is the primary even when the switch is
                    # unset, which it often is on older enumerations.
                    primary_code = taxonomies[0]["code"]
                else:
                    primary_code = None

                entity_raw = cell(raw, "entity_type")
                entity_type = int(entity_raw) if entity_raw in {"1", "2"} else None
                if entity_type is None:
                    self.deactivated_stubs += 1

                yield {
                    "npi": npi,
                    "entity_type": entity_type,
                    "replacement_npi": _npi_or_none(cell(raw, "replacement_npi")),
                    "organization_name": cell(raw, "organization_name") or None,
                    "other_organization_name": cell(raw, "other_organization_name") or None,
                    "last_name": cell(raw, "last_name") or None,
                    "first_name": cell(raw, "first_name") or None,
                    "middle_name": cell(raw, "middle_name") or None,
                    "name_prefix": cell(raw, "name_prefix") or None,
                    "name_suffix": cell(raw, "name_suffix") or None,
                    "credential": cell(raw, "credential") or None,
                    "practice_address_line1": cell(raw, "practice_address_line1") or None,
                    "practice_address_line2": cell(raw, "practice_address_line2") or None,
                    "practice_city": cell(raw, "practice_city") or None,
                    "practice_state": cell(raw, "practice_state").upper() or None,
                    "practice_postal_code": cell(raw, "practice_postal_code") or None,
                    "practice_country_code": cell(raw, "practice_country_code").upper() or None,
                    "practice_phone": cell(raw, "practice_phone") or None,
                    "enumeration_date": _date(cell(raw, "enumeration_date")),
                    "last_update_date": _date(cell(raw, "last_update_date")),
                    "certification_date": _date(cell(raw, "certification_date")),
                    "deactivation_reason_code": cell(raw, "deactivation_reason_code") or None,
                    "deactivation_date": _date(cell(raw, "deactivation_date")),
                    "reactivation_date": _date(cell(raw, "reactivation_date")),
                    "is_sole_proprietor": _flag(cell(raw, "is_sole_proprietor")),
                    "is_organization_subpart": _flag(cell(raw, "is_organization_subpart")),
                    "parent_organization_lbn": cell(raw, "parent_organization_lbn") or None,
                    "authorized_official_last_name": (
                        cell(raw, "authorized_official_last_name") or None
                    ),
                    "authorized_official_first_name": (
                        cell(raw, "authorized_official_first_name") or None
                    ),
                    "authorized_official_middle_name": (
                        cell(raw, "authorized_official_middle_name") or None
                    ),
                    "authorized_official_title": cell(raw, "authorized_official_title") or None,
                    "authorized_official_phone": cell(raw, "authorized_official_phone") or None,
                    "primary_taxonomy_code": primary_code,
                    "taxonomies": json.dumps(taxonomies, sort_keys=True, separators=(",", ":")),
                }

    def identity_key(self, row: dict[str, Any]) -> str:
        """An NPI is its own identity."""
        return str(row["npi"])

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Every loaded column except the key."""
        return tuple(row.get(c) for c in STAGING_COLUMNS if c != "npi")

    # ------------------------------------------------------------------ load

    def _table_is_empty(self, conn: Any) -> bool:
        with conn.cursor() as cur:
            cur.execute("select not exists (select 1 from nppes_providers)")
            row = cur.fetchone()
        return bool(row and row[0])

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then upsert the NPIs that moved.

        THE CHANGE SET IS SAFE TO STAGE HERE, unlike the DAC and revalidation
        files. Those reduce many rows to one with ``distinct on`` and need every
        row of a group to choose correctly; NPPES is one row per NPI, so the
        rows that moved are exactly the rows to write. Staging only the change
        set is what keeps a steady-state month from rewriting ~9M rows.

        Two cases stage the full file instead:

        * the table is empty while the diff state says rows are unchanged --
          the diff state survived a database rebuild, and staging the change
          set would leave the table empty forever;
        * keys vanished (``rows_removed``): the NPI list of the full file is
          staged to mark the missing ones ``absent_since``. Only the NPI column
          is staged for that, not the rows.

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
                    "member": self.member_name,
                    "rows_read": self.rows_read,
                    "rows_rejected_bad_npi": self.rows_rejected,
                    "deactivated_stubs": self.deactivated_stubs,
                    "taxonomy_slots": self.taxonomy_slots,
                    "lines_decoded_latin1": self.decode_stats.latin1_lines,
                    "missing_optional_fields": self.missing_optional_fields,
                    "rows_new": diff.rows_new,
                    "rows_changed": diff.rows_changed,
                    "rows_removed": diff.rows_removed,
                },
                match_keys={"npi": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            full_stage = diff.rows_unchanged > 0 and self._table_is_empty(conn)
            if full_stage:
                self.log.warning(
                    "nppes_providers is empty but the diff state is not; staging the full "
                    "file so the table is rebuilt"
                )
            if not (diff.has_changes or diff.rows_removed or full_stage):
                self.log.info("no NPPES rows moved; evidence recorded, nothing derived")
                return

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            rows = self.parse(self.fetched_path) if full_stage else diff.iter_rows()
            staged = copy_from_csv(
                conn,
                "stg_nppes",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in rows),
                batch_size=self.settings.copy_batch_size,
            )
            with conn.cursor() as cur:
                cur.execute("analyze stg_nppes")
                cur.execute(_UPSERT, {"evidence_id": evidence_id})
                upserted = cur.rowcount

            marked = 0
            if diff.rows_removed:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_PRESENT)
                copy_from_csv(
                    conn,
                    "stg_nppes_present",
                    ("npi",),
                    ((row["npi"],) for row in self.parse(self.fetched_path)),
                    batch_size=self.settings.copy_batch_size,
                )
                with conn.cursor() as cur:
                    cur.execute("create index on stg_nppes_present (npi)")
                    cur.execute("analyze stg_nppes_present")
                    cur.execute(_MARK_ABSENT)
                    marked = cur.rowcount

            self.log.info(
                "nppes staged=%s upserted=%s marked_absent=%s (full_stage=%s)",
                f"{staged:,}",
                f"{upserted:,}",
                f"{marked:,}",
                full_stage,
            )
