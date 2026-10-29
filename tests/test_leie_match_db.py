"""LEIE name + state candidates and the NPPES weekly load, against Postgres.

Each test builds a scratch database (every migration and seed, like CI) and runs
the connectors as ``app_ingest``, the role the real ingest uses, so the grants
on ``app.name_key`` and ``leie_npi_candidates`` are exercised, not assumed. All
names and NPIs are invented.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import psycopg
import pytest

from clinician_standing.config import Settings
from clinician_standing.connectors.nppes import NppesConnector
from clinician_standing.connectors.nppes_weekly import NppesWeeklyConnector
from clinician_standing.connectors.oig_leie import OigLeieConnector
from clinician_standing.leie_match import name_key
from conftest import database_url
from test_directory_connectors import nppes_row, write_nppes_zip
from test_sample_ingest import scratch_db  # noqa: F401  (pytest fixture)

pytestmark = pytest.mark.database

LEIE_HEADER = [
    "LASTNAME",
    "FIRSTNAME",
    "MIDNAME",
    "BUSNAME",
    "GENERAL",
    "SPECIALTY",
    "UPIN",
    "NPI",
    "DOB",
    "ADDRESS",
    "CITY",
    "STATE",
    "ZIP",
    "EXCLTYPE",
    "EXCLDATE",
    "REINDATE",
    "WAIVERDATE",
    "WVRSTATE",
]


def _person(
    npi: str,
    last: str,
    first: str,
    *,
    middle: str = "",
    state: str = "",
    license_state: str = "",
    updated: str = "01/02/2026",
    entity: str = "1",
) -> list[str]:
    return nppes_row(
        npi,
        **{
            "Entity Type Code": entity,
            "Provider Last Name (Legal Name)": last if entity == "1" else "",
            "Provider Organization Name (Legal Business Name)": last if entity == "2" else "",
            "Provider First Name": first,
            "Provider Middle Name": middle,
            "Provider Business Practice Location Address State Name": state,
            "Last Update Date": updated,
            "Healthcare Provider Taxonomy Code_1": "363L00000X",
            "Provider License Number State Code_1": license_state,
        },
    )


NPPES_PEOPLE = [
    _person("1990002001", "SAMPLEMATCH", "ALPHA", middle="MARIE", state="NY"),
    _person("1990002002", "COMMONTEST", "BETA", state="NJ"),
    _person("1990002003", "COMMONTEST", "BETA", state="PA", license_state="NJ"),
    _person("1990002004", "COMMONTEST", "BETA", state="CA"),
    _person("1990002005", "MIDCONFLICT", "GAMMA", middle="YVES", state="TX"),
    _person("1990002006", "ONEIL SMITH", "DELTA", state="FL"),
    _person("1990002007", "SAMPLEMATCH", "", state="NY", entity="2"),
]


def _leie_row(
    last: str,
    first: str,
    middle: str,
    state: str,
    npi: str = "0000000000",
    busname: str = "",
    excl: str = "20250115",
) -> list[str]:
    values = dict.fromkeys(LEIE_HEADER, "")
    values.update(
        LASTNAME=last,
        FIRSTNAME=first,
        MIDNAME=middle,
        BUSNAME=busname,
        GENERAL="IND- LIC HC SERV PRO",
        SPECIALTY="SYNTHETIC",
        NPI=npi,
        DOB="19700101" if last else "",
        STATE=state,
        EXCLTYPE="1128b4",
        EXCLDATE=excl,
        REINDATE="00000000",
        WAIVERDATE="00000000",
    )
    return [values[h] for h in LEIE_HEADER]


LEIE_ROWS = [
    _leie_row("SAMPLEMATCH", "ALPHA", "M", "NY"),  # one candidate, middle agrees
    _leie_row("COMMONTEST", "BETA", "", "NJ"),  # two candidates (practice, license)
    _leie_row("MIDCONFLICT", "GAMMA", "X", "TX"),  # middle initial conflicts: none
    _leie_row("O'NEIL-SMITH JR", "DELTA", "", "FL"),  # surname normalization
    _leie_row("NOBODYTEST", "EPSILON", "", "NY"),  # nobody in NPPES
    _leie_row("", "", "", "NY", busname="SAMPLEMATCH LLC"),  # business row: ignored
    _leie_row("SAMPLEMATCH", "ALPHA", "", "NY", npi="1990002001"),  # has an NPI: not a candidate
]


def _write_leie(path: Path, rows: list[list[str]]) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(LEIE_HEADER)
    writer.writerows(rows)
    path.write_bytes(buffer.getvalue().encode("latin-1"))
    return path


def _settings(tmp_path: Path, url: str) -> Settings:
    return Settings(
        database_url=url, storage_path=str(tmp_path / "storage"), work_dir=tmp_path / "work"
    )


def _run(cls, settings: Settings, monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv(f"LOCAL_SOURCE_{cls.key.upper()}", str(path))
    result = cls(settings).run()
    assert result.ok, result.error


def _rows(url: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


_LIVE = """
select leie_last_name, npi, match_confidence::float, candidate_count,
       match_detail ->> 'first_name', match_detail ->> 'middle_name', match_detail ->> 'state',
       review_status
from leie_npi_candidates
where superseded_at is null
order by leie_last_name, npi
"""


def test_leie_rows_without_npi_get_reviewable_candidates_and_no_sanctions(
    scratch_db: tuple[str, str],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url, ingest_url = scratch_db
    settings = _settings(tmp_path, ingest_url)

    # LEIE before NPPES: nothing to match against, so nothing is written and the
    # evidence says the step did not run.
    leie = _write_leie(tmp_path / "leie1.csv", LEIE_ROWS)
    _run(OigLeieConnector, settings, monkeypatch, leie)
    assert _rows(admin_url, "select count(*) from leie_npi_candidates") == [(0,)]
    assert _rows(
        admin_url,
        "select parsed ->> 'name_state_matching_ran' from evidence "
        "where source_key = 'oig_leie' and match_keys ->> 'method' = 'bulk_file'",
    ) == [("false",)]

    _run(NppesConnector, settings, monkeypatch, write_nppes_zip(tmp_path / "m.zip", NPPES_PEOPLE))
    leie2 = _write_leie(tmp_path / "leie2.csv", [*LEIE_ROWS, _leie_row("ZZTEST", "Z", "", "NY")])
    _run(OigLeieConnector, settings, monkeypatch, leie2)

    assert _rows(admin_url, _LIVE) == [
        ("COMMONTEST", "1990002002", 0.35, 2, "exact", "unknown", "practice", "needs_review"),
        ("COMMONTEST", "1990002003", 0.35, 2, "exact", "unknown", "license", "needs_review"),
        ("O'NEIL-SMITH JR", "1990002006", 0.7, 1, "exact", "unknown", "practice", "needs_review"),
        ("SAMPLEMATCH", "1990002001", 0.85, 1, "exact", "agrees", "practice", "needs_review"),
    ]
    # Never an exclusion: no roster clinicians here, and nothing at all in sanctions.
    assert _rows(admin_url, "select count(*) from sanctions") == [(0,)]
    [(parsed,)] = _rows(
        admin_url,
        "select parsed from evidence where source_key = 'oig_leie' "
        "and match_keys ->> 'method' = 'bulk_file' order by created_at desc limit 1",
    )
    assert parsed["name_state_matching_ran"] is True
    assert parsed["rows_without_npi_eligible"] == 6
    assert parsed["rows_without_npi_with_candidates"] == 3
    assert parsed["name_state_candidates_written"] == 4
    assert parsed["rows_total"] == 8

    # A reviewer rejects one. The next run keeps the decision.
    with psycopg.connect(admin_url) as conn:
        conn.execute(
            "update leie_npi_candidates set review_status = 'rejected', reviewed_at = now(), "
            "reviewed_by = 'test' where npi = '1990002003'"
        )
    leie3 = _write_leie(tmp_path / "leie3.csv", [r for r in LEIE_ROWS if r[0] != "SAMPLEMATCH"])
    _run(OigLeieConnector, settings, monkeypatch, leie3)
    assert _rows(
        admin_url, "select review_status from leie_npi_candidates where npi = '1990002003'"
    ) == [("rejected",)]
    # SAMPLEMATCH left the file: its candidate is superseded, not deleted.
    assert _rows(
        admin_url,
        "select superseded_at is not null from leie_npi_candidates where npi = '1990002001'",
    ) == [(True,)]
    assert [r[1] for r in _rows(admin_url, _LIVE)] == ["1990002002", "1990002003", "1990002006"]


def test_weekly_applies_newer_rows_and_never_rolls_back(
    scratch_db: tuple[str, str],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url, ingest_url = scratch_db
    settings = _settings(tmp_path, ingest_url)
    _run(NppesConnector, settings, monkeypatch, write_nppes_zip(tmp_path / "m.zip", NPPES_PEOPLE))

    weekly = write_nppes_zip(
        tmp_path / "wk.zip",
        [
            # Newer: applies.
            _person(
                "1990002001", "SAMPLEMATCH", "ALPHA", middle="MAE", state="NJ", updated="10/20/2026"
            ),
            # Older than the stored row: skipped.
            _person("1990002002", "COMMONTEST", "BETA", state="WY", updated="01/01/2020"),
            # New NPI: inserted.
            _person("1990002099", "WEEKLYTEST", "ZETA", state="OR", updated="10/21/2026"),
            # Deactivation stub: applies, keeps the name.
            nppes_row("1990002005", **{"NPI Deactivation Date": "10/22/2026"}),
        ],
    )
    _run(NppesWeeklyConnector, settings, monkeypatch, weekly)

    got = {
        r[0]: r[1:]
        for r in _rows(
            admin_url,
            "select npi, middle_name, practice_state, last_name, is_active, absent_since "
            "from nppes_providers order by npi",
        )
    }
    assert got["1990002001"][:2] == ("MAE", "NJ")
    assert got["1990002002"][1] == "NJ"
    assert got["1990002099"][2] == "WEEKLYTEST"
    assert got["1990002005"][2:4] == ("MIDCONFLICT", False)
    # Rows missing from the weekly file are not marked absent.
    assert all(v[4] is None for v in got.values())
    assert _rows(
        admin_url,
        "select parsed ->> 'incremental' from evidence where source_key = 'nppes_weekly'",
    ) == [("true",)]
    assert _rows(
        admin_url,
        "select deactivation_date from nppes_providers where npi = '1990002005'",
    ) == [(date(2026, 10, 22),)]


def test_sql_name_key_matches_python() -> None:
    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    names = [
        "O'Brien",
        "Peña",
        "PEÑA-SAMPLE",
        "García-López III",
        "smith jr.",
        "SMITH, SR",
        "JR",
        "",
        "  ",
        "Łukasz",
        "Strauß",
        "d'Angelo IV",
        "VAN DER BERG",
    ]
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        for raw in names:
            cur.execute("select app.name_key(%s)", (raw,))
            row = cur.fetchone()
            assert row is not None
            assert row[0] == name_key(raw), raw


def test_candidates_table_rejects_a_confidence_of_one() -> None:
    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into leie_npi_candidates (leie_key, npi, leie_last_name, leie_state, "
                "match_confidence, candidate_count) values ('x', '1990002001', 'T', 'NY', 1.0, 1)"
            )
        conn.rollback()


def test_candidates_table_is_closed_to_delivery_and_portal_roles() -> None:
    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    [(rows,)] = _rows(
        url,
        "select count(*) from information_schema.role_table_grants "
        "where table_name = 'leie_npi_candidates' "
        "and grantee in ('app_delivery', 'app_client_portal', 'anon', 'authenticated')",
    )
    assert rows == 0
