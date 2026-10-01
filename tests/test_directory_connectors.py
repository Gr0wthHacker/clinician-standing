"""Directory-layer connectors: NPPES, hospitals, facility affiliations, DAC enrichment.

No network and no database here. The end-to-end loads against Postgres are in
``test_directory_load.py`` under the ``database`` marker.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from clinician_standing.config import Settings
from clinician_standing.connectors import CONNECTORS, connector_keys
from clinician_standing.connectors._provider_data import discover_csv, normalize_ccn
from clinician_standing.connectors.base import ConnectorError
from clinician_standing.connectors.cms_dac import CmsDacConnector, _graduation_year
from clinician_standing.connectors.cms_facility_affiliation import (
    CmsFacilityAffiliationConnector,
)
from clinician_standing.connectors.cms_hospitals import CmsHospitalsConnector
from clinician_standing.connectors.nppes import (
    DESCRIPTIVE_COLUMNS,
    STAGING_COLUMNS,
    STATUS_COLUMNS,
    NppesConnector,
    find_replicate_link,
    normalize_header,
)
from clinician_standing.parse import DecodeStats, decode_lines

# --------------------------------------------------------------------------
# fixtures: tiny files in each publisher's own shape
# --------------------------------------------------------------------------

NPPES_HEADER = [
    "NPI",
    "Entity Type Code",
    "Replacement NPI",
    "Employer Identification Number (EIN)",
    "Provider Organization Name (Legal Business Name)",
    "Provider Last Name (Legal Name)",
    "Provider First Name",
    "Provider Middle Name",
    "Provider Name Prefix Text",
    "Provider Name Suffix Text",
    "Provider Credential Text",
    "Provider Other Organization Name",
    "Provider First Line Business Practice Location Address",
    "Provider Second Line Business Practice Location Address",
    "Provider Business Practice Location Address City Name",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
    "Provider Business Practice Location Address Country Code (If outside U.S.)",
    "Provider Business Practice Location Address Telephone Number",
    "Provider Enumeration Date",
    "Last Update Date",
    "NPI Deactivation Reason Code",
    "NPI Deactivation Date",
    "NPI Reactivation Date",
    "Authorized Official Last Name",
    "Authorized Official First Name",
    "Authorized Official Middle Name",
    "Authorized Official Title or Position",
    "Authorized Official Telephone Number",
    *[
        name
        for slot in (1, 2, 3)
        for name in (
            f"Healthcare Provider Taxonomy Code_{slot}",
            f"Provider License Number_{slot}",
            f"Provider License Number State Code_{slot}",
            f"Healthcare Provider Primary Taxonomy Switch_{slot}",
        )
    ],
    "Is Sole Proprietor",
    "Is Organization Subpart",
    "Parent Organization LBN",
    "Parent Organization TIN",
    "Healthcare Provider Taxonomy Group_1",
    "Healthcare Provider Taxonomy Group_2",
    "Healthcare Provider Taxonomy Group_3",
    "Certification Date",
]


def nppes_row(npi: str, **values: str) -> list[str]:
    """A row in NPPES_HEADER order; unspecified columns blank."""
    row = dict.fromkeys(NPPES_HEADER, "")
    row["NPI"] = npi
    row.update(values)
    return [row[h] for h in NPPES_HEADER]


INDIVIDUAL = nppes_row(
    "1598027682",
    **{
        "Entity Type Code": "1",
        "Employer Identification Number (EIN)": "<UNAVAIL>",
        "Provider Last Name (Legal Name)": "PEÑA",
        "Provider First Name": "ANA",
        "Provider Credential Text": "M.D.",
        "Provider First Line Business Practice Location Address": "2279 CONEY ISLAND AVE",
        "Provider Business Practice Location Address City Name": "BROOKLYN",
        "Provider Business Practice Location Address State Name": "ny",
        "Provider Business Practice Location Address Postal Code": "112233456",
        "Provider Business Practice Location Address Country Code (If outside U.S.)": "US",
        "Provider Enumeration Date": "06/13/2012",
        "Last Update Date": "04/25/2025",
        "Healthcare Provider Taxonomy Code_1": "2084P0800X",
        "Provider License Number_1": "123456",
        "Provider License Number State Code_1": "NJ",
        "Healthcare Provider Primary Taxonomy Switch_1": "N",
        "Healthcare Provider Taxonomy Code_2": "2084N0400X",
        "Provider License Number_2": "654321",
        "Provider License Number State Code_2": "NY",
        "Healthcare Provider Primary Taxonomy Switch_2": "Y",
        "Is Sole Proprietor": "N",
        "Certification Date": "04/25/2025",
    },
)

ORGANIZATION = nppes_row(
    "1234567893",
    **{
        "Entity Type Code": "2",
        "Provider Organization Name (Legal Business Name)": "BROOKLYN NEUROLOGY PC",
        "Provider Business Practice Location Address State Name": "NY",
        "Last Update Date": "01/02/2024",
        "Authorized Official Last Name": "SMITH",
        "Authorized Official First Name": "JO",
        "Authorized Official Title or Position": "PRESIDENT",
        "Healthcare Provider Taxonomy Code_1": "261QM1300X",
        "Is Organization Subpart": "X",
        "Parent Organization TIN": "987650001",
    },
)

DEACTIVATED = nppes_row("1003000126", **{"NPI Deactivation Date": "05/01/2020"})


def write_nppes_csv(path: Path, rows: list[list[str]], *, latin1_row: bool = False) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(NPPES_HEADER)
    for row in rows:
        writer.writerow(row)
    payload = buffer.getvalue().encode("utf-8")
    if latin1_row:
        extra = io.StringIO()
        csv.writer(extra, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(
            nppes_row(
                "1730291054",
                **{
                    "Entity Type Code": "2",
                    "Provider Organization Name (Legal Business Name)": "CAFÉ CLINIC",
                },
            )
        )
        payload += extra.getvalue().encode("latin-1")
    path.write_bytes(payload)
    return path


def write_nppes_zip(path: Path, rows: list[list[str]]) -> Path:
    csv_path = write_nppes_csv(path.with_suffix(".csv"), rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("npidata_pfile_20050523-20260914_fileheader.csv", ",".join(NPPES_HEADER))
        archive.write(csv_path, "npidata_pfile_20050523-20260914.csv")
        archive.writestr("pl_pfile_20050523-20260914.csv", "NPI\n")
    csv_path.unlink()
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=None,
        storage_path=str(tmp_path / "storage"),
        work_dir=tmp_path / "work",
    )


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


def test_new_connectors_are_registered_and_nursys_still_runs_last() -> None:
    keys = connector_keys()
    for key in ("nppes", "cms_hospitals", "cms_facility_affiliation"):
        assert key in CONNECTORS
    assert keys[0] == "cms_dac"
    assert keys[-1] == "nursys"
    assert keys.index("cms_hospitals") < keys.index("cms_facility_affiliation")


def test_directory_connectors_never_claim_their_own_authority() -> None:
    # A connector never asserts primacy; the registry does (base.ensure_registered).
    assert CmsHospitalsConnector.is_primary_source is False
    assert CmsFacilityAffiliationConnector.is_primary_source is False


# --------------------------------------------------------------------------
# decode_lines
# --------------------------------------------------------------------------


def test_decode_lines_utf8_round_trips_and_strips_bom() -> None:
    stats = DecodeStats()
    lines = list(decode_lines([b"\xef\xbb\xbfNPI\n", "PEÑA\n".encode()], stats))
    assert lines == ["NPI\n", "PEÑA\n"]
    assert stats.lines == 2 and stats.latin1_lines == 0


def test_decode_lines_falls_back_to_latin1_per_line_without_dropping_characters() -> None:
    stats = DecodeStats()
    lines = list(decode_lines([b"ok\n", "PEÑA\n".encode("latin-1")], stats))
    assert lines == ["ok\n", "PEÑA\n"]
    assert stats.latin1_lines == 1


def test_decode_lines_feeds_csv_a_quoted_field_spanning_lines() -> None:
    raw = [b'"a","line one\n', b'line two"\n', b'"b","c"\n']
    rows = list(csv.reader(decode_lines(raw)))
    assert rows == [["a", "line one\nline two"], ["b", "c"]]


# --------------------------------------------------------------------------
# NPPES
# --------------------------------------------------------------------------

V2_PAGE = """
<a href="./NPPES_Data_Dissemination_September_2026.zip">V1</a>
<a href="NPPES_Data_Dissemination_September_2026_V2.zip">V2</a>
<a href="NPPES_Data_Dissemination_091426_092026_Weekly_V2.zip">weekly</a>
<a href="NPPES_Deactivated_NPI_Report_091426_V2.zip">deactivated</a>
"""


def test_replicate_link_prefers_v2_and_resolves_relative_urls() -> None:
    assert (
        find_replicate_link(V2_PAGE)
        == "https://download.cms.gov/nppes/NPPES_Data_Dissemination_September_2026_V2.zip"
    )


def test_replicate_link_falls_back_to_v1_and_ignores_weekly_and_deactivation_files() -> None:
    page = V2_PAGE.replace("_September_2026_V2.zip", "_x.zip")
    assert find_replicate_link(page) == (
        "https://download.cms.gov/nppes/NPPES_Data_Dissemination_September_2026.zip"
    )
    only_weekly = '<a href="NPPES_Data_Dissemination_091426_092026_Weekly_V2.zip">w</a>'
    assert find_replicate_link(only_weekly) is None


def test_replicate_link_off_the_allowlist_is_refused(settings: Settings) -> None:
    connector = NppesConnector(settings)
    connector.fetch_text = lambda _url, **_kw: (  # type: ignore[method-assign]
        '<a href="https://evil.example/NPPES_Data_Dissemination_September_2026_V2.zip">x</a>'
    )
    with pytest.raises(ConnectorError, match="allowlist"):
        connector.discover_download_url()


def test_fetch_text_refuses_plain_http(settings: Settings) -> None:
    with pytest.raises(ConnectorError, match="https"):
        NppesConnector(settings).fetch_text("http://download.cms.gov/nppes/NPI_Files.html")


def test_normalize_header_tolerates_punctuation_and_case() -> None:
    assert normalize_header(
        "Provider Business Practice Location Address Country Code (If outside U.S.)"
    ) == normalize_header("provider business practice location address country code if outside us")


def test_nppes_parse_individual_organization_and_stub(tmp_path: Path, settings: Settings) -> None:
    path = write_nppes_csv(tmp_path / "npidata.csv", [INDIVIDUAL, ORGANIZATION, DEACTIVATED])
    connector = NppesConnector(settings)
    rows = {r["npi"]: r for r in connector.parse(path)}

    person = rows["1598027682"]
    assert person["entity_type"] == 1
    assert person["last_name"] == "PEÑA"
    assert person["practice_state"] == "NY"
    assert person["enumeration_date"].isoformat() == "2012-06-13"
    # The switch says slot 2 is primary, not slot 1.
    assert person["primary_taxonomy_code"] == "2084N0400X"
    taxonomies = json.loads(person["taxonomies"])
    assert [(t["code"], t["license_state"], t["primary"]) for t in taxonomies] == [
        ("2084P0800X", "NJ", False),
        ("2084N0400X", "NY", True),
    ]
    assert person["is_sole_proprietor"] is False

    org = rows["1234567893"]
    assert org["entity_type"] == 2
    assert org["authorized_official_title"] == "PRESIDENT"
    # A single taxonomy is primary even without the switch.
    assert org["primary_taxonomy_code"] == "261QM1300X"
    # "X" means not answered.
    assert org["is_organization_subpart"] is None

    stub = rows["1003000126"]
    assert stub["entity_type"] is None
    assert stub["deactivation_date"].isoformat() == "2020-05-01"
    assert json.loads(stub["taxonomies"]) == []
    assert connector.deactivated_stubs == 1


def test_nppes_never_loads_ein_or_parent_tin(tmp_path: Path, settings: Settings) -> None:
    path = write_nppes_csv(tmp_path / "npidata.csv", [ORGANIZATION])
    (row,) = list(NppesConnector(settings).parse(path))
    assert "987650001" not in json.dumps(row, default=str)
    assert not any(k == "ein" or "tin" in k for k in row)


def test_nppes_parse_reads_the_data_member_out_of_the_zip(
    tmp_path: Path, settings: Settings
) -> None:
    path = write_nppes_zip(
        tmp_path / "NPPES_Data_Dissemination_September_2026_V2.zip", [INDIVIDUAL]
    )
    connector = NppesConnector(settings)
    rows = list(connector.parse(path))
    assert [r["npi"] for r in rows] == ["1598027682"]
    assert connector.member_name == "npidata_pfile_20050523-20260914.csv"


def test_nppes_zip_without_a_data_member_fails_loudly(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "nothing here")
    with pytest.raises(ConnectorError, match="npidata_pfile"):
        list(NppesConnector(settings).parse(path))


def test_nppes_latin1_line_is_decoded_not_dropped(tmp_path: Path, settings: Settings) -> None:
    path = write_nppes_csv(tmp_path / "npidata.csv", [INDIVIDUAL], latin1_row=True)
    connector = NppesConnector(settings)
    names = {r["npi"]: r["organization_name"] for r in connector.parse(path)}
    assert names["1730291054"] == "CAFÉ CLINIC"
    assert connector.decode_stats.latin1_lines == 1


def test_nppes_missing_required_column_fails_loudly(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "npidata.csv"
    path.write_text('"NPI","Provider First Name"\n"1598027682","ANA"\n', encoding="utf-8")
    with pytest.raises(ConnectorError, match="Entity Type Code"):
        list(NppesConnector(settings).parse(path))


def test_nppes_bad_npi_is_rejected_not_loaded(tmp_path: Path, settings: Settings) -> None:
    path = write_nppes_csv(tmp_path / "npidata.csv", [nppes_row("12345"), INDIVIDUAL])
    connector = NppesConnector(settings)
    assert [r["npi"] for r in connector.parse(path)] == ["1598027682"]
    assert connector.rows_rejected == 1


def test_nppes_rerun_over_unchanged_file_reports_no_changes(
    tmp_path: Path, settings: Settings
) -> None:
    path = write_nppes_csv(tmp_path / "npidata.csv", [INDIVIDUAL, ORGANIZATION, DEACTIVATED])
    first = NppesConnector(settings)
    diff = first.diff(first._reiterable_rows(path))
    assert diff.rows_new == 3
    first._promote_state(diff)

    # Reordered rows, same content: still nothing moved.
    reordered = write_nppes_csv(tmp_path / "again.csv", [DEACTIVATED, ORGANIZATION, INDIVIDUAL])
    second = NppesConnector(settings)
    again = second.diff(second._reiterable_rows(reordered))
    assert (again.rows_new, again.rows_changed, again.rows_removed) == (0, 0, 0)


def test_nppes_upsert_column_lists_partition_the_staging_columns() -> None:
    # Every staged column is either descriptive (kept on a stub) or status
    # (always taken), never both and never neither -- or the upsert drops it.
    rest = set(STAGING_COLUMNS) - {"npi"}
    assert set(DESCRIPTIVE_COLUMNS) | set(STATUS_COLUMNS) == rest
    assert not set(DESCRIPTIVE_COLUMNS) & set(STATUS_COLUMNS)
    assert "deactivation_date" in STATUS_COLUMNS
    assert "last_name" in DESCRIPTIVE_COLUMNS


# --------------------------------------------------------------------------
# provider-data helpers
# --------------------------------------------------------------------------

CSV_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "b7c4080ae144663e43353a9c35cd3f53_1787091342/Facility_Affiliation.csv"
)


@pytest.mark.parametrize(
    "document",
    [
        {
            "modified": "2026-08-18",
            "distribution": [{"mediaType": "text/csv", "downloadURL": CSV_URL}],
        },
        {"distribution": [{"data": {"mediaType": "text/csv", "downloadURL": CSV_URL}}]},
        {"distribution": [{"downloadURL": CSV_URL}]},
    ],
)
def test_discover_csv_accepts_both_metastore_shapes(document: dict, settings: Settings) -> None:
    connector = CmsFacilityAffiliationConnector(settings)
    connector.fetch_json = lambda _url: document  # type: ignore[method-assign]
    assert discover_csv(connector, "27ea-46a8").url == CSV_URL


def test_discover_csv_refuses_a_url_off_the_allowlist(settings: Settings) -> None:
    connector = CmsHospitalsConnector(settings)
    connector.fetch_json = lambda _url: {  # type: ignore[method-assign]
        "distribution": [{"mediaType": "text/csv", "downloadURL": "https://evil.example/x.csv"}]
    }
    with pytest.raises(ConnectorError, match="allowlist"):
        discover_csv(connector, "xubh-q36u")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("090012", "090012"),
        ("90012", "090012"),  # lost its leading zero in a spreadsheet
        ("33t241", "33T241"),
        (" 330241 ", "330241"),
        ("", None),
        ("1234567", None),
        ("12-345", None),
    ],
)
def test_normalize_ccn(raw: str, expected: str | None) -> None:
    assert normalize_ccn(raw) == expected


# --------------------------------------------------------------------------
# hospitals
# --------------------------------------------------------------------------

HOSPITAL_HEADER = (
    "Facility ID,Facility Name,Address,City/Town,State,ZIP Code,County/Parish,"
    "Telephone Number,Hospital Type,Hospital Ownership,Emergency Services,"
    "Meets criteria for birthing friendly designation,Hospital overall rating\n"
)


def test_hospitals_parse(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "hospitals.csv"
    path.write_bytes(
        b"\xef\xbb\xbf"
        + (
            HOSPITAL_HEADER
            + "010001,SOUTHEAST HEALTH MEDICAL CENTER,1108 ROSS CLARK CIRCLE,DOTHAN,AL,36301,"
            'HOUSTON,(334) 793-8701,Acute Care Hospitals,"Government - Hospital District or '
            'Authority",Yes,Y,4\n'
            "330241,KINGS COUNTY HOSPITAL,451 CLARKSON AVE,BROOKLYN,NY,11203,KINGS,,"
            "Acute Care Hospitals,Government - Local,No,,Not Available\n"
            ",NO CCN,,,,,,,,,,,\n"
        ).encode()
    )
    connector = CmsHospitalsConnector(settings)
    rows = {r["ccn"]: r for r in connector.parse(path)}
    assert set(rows) == {"010001", "330241"}
    assert rows["010001"]["overall_rating"] == 4
    assert rows["010001"]["emergency_services"] is True
    assert rows["330241"]["overall_rating"] is None
    assert rows["330241"]["emergency_services"] is False
    assert connector.rows_rejected == 1


def test_hospitals_missing_ccn_column_fails_loudly(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "hospitals.csv"
    path.write_text("Name,State\nX,AL\n", encoding="utf-8")
    with pytest.raises(ConnectorError, match="Facility ID"):
        list(CmsHospitalsConnector(settings).parse(path))


# --------------------------------------------------------------------------
# facility affiliations
# --------------------------------------------------------------------------

AFFILIATION_HEADER = (
    "NPI,Ind_PAC_ID,Provider Last Name,Provider First Name,Provider Middle Name,suff,"
    "facility_type,Facility Affiliations Certification Number,"
    "Facility Type Certification Number\n"
)


def test_facility_affiliations_parse(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "aff.csv"
    path.write_text(
        AFFILIATION_HEADER
        + "1003000126,7517003643,ENKESHAFI,ARDALAN,,,Hospital,090012,\n"
        + "1003000126,7517003643,ENKESHAFI,ARDALAN,,,Inpatient rehabilitation facility,"
        "33T241,330241\n"
        + "12345,1,BAD,NPI,,,Hospital,090012,\n"
        + "1003000142,9931380672,KHALIL,RASHID,,,Hospital,BADCCN1,\n"
        + "1003000142,9931380672,KHALIL,RASHID,,,,360112,\n",
        encoding="utf-8",
    )
    connector = CmsFacilityAffiliationConnector(settings)
    rows = list(connector.parse(path))
    assert [(r["facility_type"], r["ccn"], r["parent_ccn"]) for r in rows] == [
        ("Hospital", "090012", None),
        ("Inpatient rehabilitation facility", "33T241", "330241"),
    ]
    assert connector.rows_rejected == 3
    keys = {connector.identity_key(r) for r in rows}
    assert len(keys) == 2


def test_facility_affiliations_missing_column_fails_loudly(
    tmp_path: Path, settings: Settings
) -> None:
    path = tmp_path / "aff.csv"
    path.write_text("NPI,facility_type\n1003000126,Hospital\n", encoding="utf-8")
    with pytest.raises(ConnectorError, match="Facility Affiliations Certification Number"):
        list(CmsFacilityAffiliationConnector(settings).parse(path))


# --------------------------------------------------------------------------
# DAC enrichment columns
# --------------------------------------------------------------------------

DAC_HEADER = [
    "NPI",
    "Ind_PAC_ID",
    "Ind_enrl_ID",
    "Provider Last Name",
    "Provider First Name",
    "Provider Middle Name",
    "suff",
    "gndr",
    "Cred",
    "Med_sch",
    "Grd_yr",
    "pri_spec",
    "sec_spec_all",
    "Telehlth",
    "Facility Name",
    "org_pac_id",
    "num_org_mem",
    "adr_ln_1",
    "adr_ln_2",
    "City/Town",
    "State",
    "ZIP Code",
    "Telephone Number",
]


def write_dac(path: Path, header: list[str], values: dict[str, str]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerow({h: values.get(h, "") for h in header})
    return path


DAC_VALUES = {
    "NPI": "1598027682",
    "Ind_PAC_ID": "1234567890",
    "Cred": "MD",
    "Med_sch": "SUNY DOWNSTATE MEDICAL CENTER COLLEGE OF MEDICINE",
    "Grd_yr": "2008",
    "pri_spec": "NEUROLOGY",
    "sec_spec_all": "CLINICAL NEUROPHYSIOLOGY, SLEEP MEDICINE",
    "Facility Name": "BROOKLYN NEUROLOGY PC",
    "org_pac_id": "0042000001",
    "State": "NY",
}


def test_dac_reads_medical_school_graduation_year_and_secondary_specialties(
    tmp_path: Path, settings: Settings
) -> None:
    path = write_dac(tmp_path / "dac.csv", DAC_HEADER, DAC_VALUES)
    connector = CmsDacConnector(settings)
    (row,) = list(connector.parse(path))
    assert row["medical_school"] == "SUNY DOWNSTATE MEDICAL CENTER COLLEGE OF MEDICINE"
    assert row["graduation_year"] == 2008
    assert row["secondary_specialties"] == "CLINICAL NEUROPHYSIOLOGY, SLEEP MEDICINE"
    assert connector.missing_optional_columns == []


def test_dac_without_the_enrichment_columns_still_ingests(
    tmp_path: Path, settings: Settings
) -> None:
    header = [h for h in DAC_HEADER if h not in {"Med_sch", "Grd_yr", "sec_spec_all"}]
    path = write_dac(tmp_path / "dac.csv", header, DAC_VALUES)
    connector = CmsDacConnector(settings)
    (row,) = list(connector.parse(path))
    assert row["medical_school"] is None and row["graduation_year"] is None
    assert set(connector.missing_optional_columns) == {"Med_sch", "Grd_yr", "sec_spec_all"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2008", 2008), ("", None), ("N/A", None), ("208", None), ("1850", None), ("3000", None)],
)
def test_graduation_year_is_bounded_to_the_column_check(raw: str, expected: int | None) -> None:
    assert _graduation_year(raw) == expected
