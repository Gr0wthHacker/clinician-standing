"""End-to-end loads of the directory connectors against a real Postgres.

Each test drives ``Connector.run()`` -- fetch through a ``LOCAL_SOURCE_*``
override, diff, plausibility floor, evidence, load, ``source_runs`` -- against
the throwaway cluster named by ``TEST_DATABASE_URL``, then reads the result back.
``run()`` commits on its own connection, so these tests cannot use the
rolled-back ``db_connection`` fixture for their writes; each one deletes what it
wrote in a ``finally`` instead, so a failure leaves the cluster as it found it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest

from clinician_standing.config import Settings
from clinician_standing.connectors.cms_dac import CmsDacConnector
from clinician_standing.connectors.cms_facility_affiliation import (
    CmsFacilityAffiliationConnector,
)
from clinician_standing.connectors.cms_hospitals import CmsHospitalsConnector
from clinician_standing.connectors.nppes import NppesConnector
from conftest import database_url
from test_directory_connectors import (
    DAC_HEADER,
    DAC_VALUES,
    DEACTIVATED,
    INDIVIDUAL,
    ORGANIZATION,
    nppes_row,
    write_dac,
    write_nppes_csv,
    write_nppes_zip,
)

pytestmark = pytest.mark.database

TEST_NPIS = ("1598027682", "1234567893", "1003000126", "1730291054", "1003000142", "1003000423")
TEST_CCNS = ("090012", "360112", "33T241", "330241", "990001")
SOURCE_KEYS = ("nppes", "cms_hospitals", "cms_facility_affiliation")


@pytest.fixture
def url() -> str:
    value = database_url()
    if value is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    return value


@pytest.fixture
def settings(url: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=url,
        storage_path=str(tmp_path / "storage"),
        work_dir=tmp_path / "work",
        keep_downloads=True,
    )


def _cleanup(url: str) -> None:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "delete from clinician_facility_affiliations where npi = any(%s)", (list(TEST_NPIS),)
        )
        cur.execute("delete from nppes_providers where npi = any(%s)", (list(TEST_NPIS),))
        cur.execute("delete from facilities where ccn = any(%s)", (list(TEST_CCNS),))
        cur.execute(
            "delete from clinicians where npi = any(%s) and ind_pac_id = 'TESTDIR'",
            (list(TEST_NPIS),),
        )
        # Only evidence nothing still cites. A cluster that also holds a real
        # load (someone pointed TEST_DATABASE_URL at a dev database) keeps its
        # evidence; the foreign keys would refuse the delete otherwise.
        cur.execute(
            """delete from evidence e
                where e.source_key = any(%s)
                  and not exists (select 1 from nppes_providers p where p.evidence_id = e.id)
                  and not exists (select 1 from facilities f where f.evidence_id = e.id)
                  and not exists (
                      select 1 from clinician_facility_affiliations a where a.evidence_id = e.id)""",
            (list(SOURCE_KEYS),),
        )
        cur.execute("delete from source_runs where source_key = any(%s)", (list(SOURCE_KEYS),))


@pytest.fixture(autouse=True)
def clean(url: str) -> Iterator[None]:
    _cleanup(url)
    try:
        yield
    finally:
        _cleanup(url)


def _run(connector_cls, settings: Settings, monkeypatch: pytest.MonkeyPatch, path: Path):
    monkeypatch.setenv(f"LOCAL_SOURCE_{connector_cls.key.upper()}", str(path))
    result = connector_cls(settings).run()
    assert result.ok, result.error
    return result


def _one(url: str, sql: str, params: tuple = ()) -> tuple:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    assert row is not None
    return row


def _all(url: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# --------------------------------------------------------------------------
# NPPES
# --------------------------------------------------------------------------


def test_nppes_loads_reruns_clean_and_keeps_names_through_a_deactivation(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = write_nppes_zip(tmp_path / "m1.zip", [INDIVIDUAL, ORGANIZATION, DEACTIVATED])
    result = _run(NppesConnector, settings, monkeypatch, first)
    assert (result.rows_in, result.rows_new) == (3, 3)

    entity, last, primary, active, states = _one(
        url,
        """select entity_type, last_name, primary_taxonomy_code, is_active,
                  (select array_agg(t->>'license_state' order by t->>'slot')
                     from jsonb_array_elements(taxonomies) t)
             from nppes_providers where npi = '1598027682'""",
    )
    assert (entity, last, primary, active) == (1, "PEÑA", "2084N0400X", True)
    assert states == ["NJ", "NY"]
    assert _one(url, "select is_active from nppes_providers where npi = '1003000126'") == (False,)
    assert _one(
        url, "select count(*) from evidence where source_key = 'nppes' and parsed ? 'member'"
    ) == (1,)

    # Same file again: a diff, not a reload.
    again = _run(NppesConnector, settings, monkeypatch, first)
    assert (again.rows_new, again.rows_changed) == (0, 0)

    # The individual is deactivated: NPPES publishes a stub with every
    # descriptive column blank. Name and taxonomy must survive it.
    stub = nppes_row("1598027682", **{"NPI Deactivation Date": "09/01/2026"})
    third = write_nppes_zip(tmp_path / "m3.zip", [stub, ORGANIZATION, DEACTIVATED])
    changed = _run(NppesConnector, settings, monkeypatch, third)
    assert changed.rows_changed == 1
    last, entity, deactivated, active, primary = _one(
        url,
        """select last_name, entity_type, deactivation_date, is_active, primary_taxonomy_code
             from nppes_providers where npi = '1598027682'""",
    )
    assert (last, entity, primary) == ("PEÑA", 1, "2084N0400X")
    assert (deactivated, active) == (date(2026, 9, 1), False)


def test_nppes_marks_an_npi_that_left_the_file_and_clears_it_on_return(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = write_nppes_csv(tmp_path / "full.csv", [INDIVIDUAL, ORGANIZATION, DEACTIVATED])
    _run(NppesConnector, settings, monkeypatch, full)

    shorter = write_nppes_csv(tmp_path / "short.csv", [INDIVIDUAL, ORGANIZATION])
    result = _run(NppesConnector, settings, monkeypatch, shorter)
    assert result.ok
    assert _one(url, "select absent_since from nppes_providers where npi = '1003000126'") == (
        date.today(),
    )
    assert _one(url, "select absent_since from nppes_providers where npi = '1598027682'") == (None,)

    _run(NppesConnector, settings, monkeypatch, full)
    assert _one(url, "select absent_since from nppes_providers where npi = '1003000126'") == (None,)


def test_nppes_rebuilds_an_emptied_table_from_surviving_diff_state(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_nppes_csv(tmp_path / "full.csv", [INDIVIDUAL, ORGANIZATION])
    _run(NppesConnector, settings, monkeypatch, path)
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("delete from nppes_providers where npi = any(%s)", (list(TEST_NPIS),))
        cur.execute("select count(*) from nppes_providers")
        row = cur.fetchone()
    if row and row[0]:
        pytest.skip("cluster holds other NPPES rows; the empty-table guard cannot be exercised")

    result = _run(NppesConnector, settings, monkeypatch, path)
    assert (result.rows_new, result.rows_changed) == (0, 0)
    assert _one(
        url, "select count(*) from nppes_providers where npi = any(%s)", (list(TEST_NPIS),)
    ) == (2,)


# --------------------------------------------------------------------------
# hospitals + facility affiliations + the directory view
# --------------------------------------------------------------------------

HOSPITALS_V1 = (
    "Facility ID,Facility Name,Address,City/Town,State,ZIP Code,County/Parish,"
    "Telephone Number,Hospital Type,Hospital Ownership,Emergency Services,"
    "Hospital overall rating\n"
    "090012,HOWARD UNIVERSITY HOSPITAL,2041 GEORGIA AVE,WASHINGTON,DC,20060,DC,,"
    "Acute Care Hospitals,Voluntary non-profit - Private,Yes,2\n"
    "330241,KINGS COUNTY HOSPITAL,451 CLARKSON AVE,BROOKLYN,NY,11203,KINGS,,"
    "Acute Care Hospitals,Government - Local,Yes,Not Available\n"
    "990001,CLOSING HOSPITAL,1 MAIN ST,NOWHERE,NY,10001,KINGS,,"
    "Acute Care Hospitals,Proprietary,No,3\n"
)

AFF_HEADER = (
    "NPI,Ind_PAC_ID,Provider Last Name,Provider First Name,Provider Middle Name,suff,"
    "facility_type,Facility Affiliations Certification Number,"
    "Facility Type Certification Number\n"
)


def _aff(*rows: str) -> str:
    return AFF_HEADER + "".join(r + "\n" for r in rows)


A_HOSP = "1598027682,1,PENA,ANA,,,Hospital,090012,"
A_IRF = "1598027682,1,PENA,ANA,,,Inpatient rehabilitation facility,33T241,330241"
B_HOSP = "1003000142,2,KHALIL,RASHID,,,Hospital,360112,"
C_HOSP = "1003000423,3,VELOTTA,JENNIFER,,,Hospital,090012,"


def test_hospitals_upsert_and_mark_the_ones_that_left(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "h1.csv"
    path.write_text(HOSPITALS_V1, encoding="utf-8")
    _run(CmsHospitalsConnector, settings, monkeypatch, path)
    assert _one(url, "select name, overall_rating from facilities where ccn = '090012'") == (
        "HOWARD UNIVERSITY HOSPITAL",
        2,
    )

    path2 = tmp_path / "h2.csv"
    path2.write_text("\n".join(HOSPITALS_V1.splitlines()[:-1]) + "\n", encoding="utf-8")
    _run(CmsHospitalsConnector, settings, monkeypatch, path2)
    assert _one(url, "select absent_since from facilities where ccn = '990001'") == (date.today(),)
    assert _one(url, "select absent_since from facilities where ccn = '090012'") == (None,)


def test_facility_affiliations_open_close_and_reopen(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    month1 = tmp_path / "a1.csv"
    month1.write_text(_aff(A_HOSP, A_IRF, B_HOSP, C_HOSP), encoding="utf-8")
    result = _run(CmsFacilityAffiliationConnector, settings, monkeypatch, month1)
    assert result.rows_new == 4

    # A leaves the rehab unit but stays in the file: that pair closes.
    # B leaves the file entirely: ambiguous, so B's row stays open.
    month2 = tmp_path / "a2.csv"
    month2.write_text(_aff(A_HOSP, C_HOSP), encoding="utf-8")
    _run(CmsFacilityAffiliationConnector, settings, monkeypatch, month2)
    rows = dict(
        _all(
            url,
            """select npi || '|' || ccn, end_date from clinician_facility_affiliations
                where npi = any(%s)""",
            (list(TEST_NPIS),),
        )
    )
    assert rows["1598027682|33T241"] == date.today()
    assert rows["1598027682|090012"] is None
    assert rows["1003000142|360112"] is None

    # A returns to the rehab unit: a new open row, the closed one kept as history.
    month3 = tmp_path / "a3.csv"
    month3.write_text(_aff(A_HOSP, A_IRF, C_HOSP), encoding="utf-8")
    _run(CmsFacilityAffiliationConnector, settings, monkeypatch, month3)
    history = _all(
        url,
        """select end_date is null from clinician_facility_affiliations
            where npi = '1598027682' and ccn = '33T241' order by end_date nulls last""",
    )
    assert history == [(False,), (True,)]


def test_clinician_directory_joins_roster_nppes_and_named_affiliations(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            """insert into clinicians (npi, ind_pac_id, clinician_type, last_name,
                                        medical_school, graduation_year)
               values ('1598027682', 'TESTDIR', 'physician', 'PENA', 'SUNY DOWNSTATE', 2008)
               on conflict (npi) do nothing"""
        )
    _run(
        NppesConnector,
        settings,
        monkeypatch,
        write_nppes_csv(tmp_path / "n.csv", [INDIVIDUAL, ORGANIZATION]),
    )
    hospitals = tmp_path / "h.csv"
    hospitals.write_text(HOSPITALS_V1, encoding="utf-8")
    _run(CmsHospitalsConnector, settings, monkeypatch, hospitals)
    affiliations = tmp_path / "a.csv"
    affiliations.write_text(_aff(A_HOSP, A_IRF), encoding="utf-8")
    _run(CmsFacilityAffiliationConnector, settings, monkeypatch, affiliations)

    in_nppes, active, states, school, year, facilities = _one(
        url,
        """select in_nppes, nppes_active, nppes_license_states, medical_school,
                  graduation_year, facility_affiliations
             from clinician_directory where npi = '1598027682'""",
    )
    assert (in_nppes, active, states) == (True, True, ["NJ", "NY"])
    assert (school, year) == ("SUNY DOWNSTATE", 2008)
    named = {(f["ccn"], f["name"]) for f in facilities}
    # The rehab unit is named by its parent hospital.
    assert named == {("090012", "HOWARD UNIVERSITY HOSPITAL"), ("33T241", "KINGS COUNTY HOSPITAL")}
    assert isinstance(json.dumps(facilities), str)


def test_directory_tables_are_closed_to_delivery_and_portal_roles(url: str) -> None:
    rows = _all(
        url,
        """select g.rolname, c.relname
             from pg_class c
             join pg_namespace n on n.oid = c.relnamespace
             cross join lateral aclexplode(c.relacl) acl
             join pg_roles g on g.oid = acl.grantee
            where n.nspname = 'public'
              and c.relname in ('nppes_providers', 'facilities',
                                'clinician_facility_affiliations', 'clinician_directory')
              and g.rolname in ('app_delivery', 'app_client_portal', 'anon', 'authenticated')""",
    )
    assert rows == []


# --------------------------------------------------------------------------
# DAC enrichment columns reach clinicians
# --------------------------------------------------------------------------


def test_dac_load_writes_medical_school_and_graduation_year(
    url: str, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {**DAC_VALUES, "NPI": "1730291054", "org_pac_id": "9900000077"}
    path = write_dac(tmp_path / "dac.csv", DAC_HEADER, values)
    monkeypatch.setenv("LOCAL_SOURCE_CMS_DAC", str(path))
    connector = CmsDacConnector(settings)
    try:
        result = connector.run()
        assert result.ok, result.error
        assert _one(
            url,
            """select medical_school, graduation_year, secondary_specialties
                 from clinicians where npi = '1730291054'""",
        ) == (
            "SUNY DOWNSTATE MEDICAL CENTER COLLEGE OF MEDICINE",
            2008,
            "CLINICAL NEUROPHYSIOLOGY, SLEEP MEDICINE",
        )
    finally:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute(
                """delete from affiliations a using clinicians c
                    where a.clinician_id = c.id and c.npi = '1730291054'"""
            )
            cur.execute("delete from clinicians where npi = '1730291054'")
            cur.execute("delete from practices where org_pac_id = '9900000077'")
            cur.execute("delete from source_runs where id = %s", (connector.run_id,))
            if connector.evidence_id is not None:
                cur.execute("delete from evidence where id = %s", (connector.evidence_id,))
