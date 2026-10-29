"""LEIE to NPPES name + state candidates, and the NPPES weekly connector.

No network and no database. The end-to-end run against Postgres, as the ingest
role, is in ``test_leie_match_db.py``. All names are invented.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clinician_standing.config import Settings
from clinician_standing.connectors import CONNECTORS, connector_keys
from clinician_standing.connectors.base import ConnectorError
from clinician_standing.connectors.nppes_weekly import (
    _WEEKLY_UPSERT,
    NppesWeeklyConnector,
    find_weekly_link,
)
from clinician_standing.leie_match import (
    ACCENTS_FROM,
    ACCENTS_TO,
    BASE_CONFIDENCE,
    MAX_CANDIDATES_PER_ROW,
    MAX_CONFIDENCE,
    LeieRow,
    MatchSummary,
    NppesPerson,
    leie_key,
    match_row,
    name_key,
)
from test_directory_connectors import INDIVIDUAL, nppes_row, write_nppes_zip

MIGRATION = Path(__file__).parent.parent / "db" / "migrations" / "0017_leie_npi_candidates.sql"


def _leie(
    last: str = "SAMPLEMATCH",
    first: str | None = "ALPHA",
    middle: str | None = None,
    state: str = "NY",
) -> LeieRow:
    return LeieRow(
        leie_key="k" * 64, last_name=last, first_name=first, middle_name=middle, state=state
    )


def _person(
    npi: str = "1990002001",
    last: str = "SAMPLEMATCH",
    first: str = "ALPHA",
    middle: str | None = None,
    practice: str | None = "NY",
    licenses: tuple[str, ...] = (),
) -> NppesPerson:
    return NppesPerson(
        npi=npi,
        last_name=last,
        first_name=first,
        middle_name=middle,
        practice_state=practice,
        license_states=licenses,
        is_active=True,
    )


# --------------------------------------------------------------------------
# name_key
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("O'Brien", "OBRIEN"),
        ("O BRIEN", "OBRIEN"),
        ("Peña", "PENA"),
        ("PEÑA", "PENA"),
        ("García-López III", "GARCIALOPEZ"),
        ("SMITH JR.", "SMITH"),
        ("SMITH, SR", "SMITH"),
        ("JR", "JR"),
        ("  ", None),
        (None, None),
        ("Łukasz", "UKASZ"),
    ],
)
def test_name_key(raw: str | None, expected: str | None) -> None:
    assert name_key(raw) == expected


def test_name_key_literals_match_the_sql_function() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert f"'{ACCENTS_FROM}',\n              '{ACCENTS_TO}'" in sql
    assert len(ACCENTS_FROM) == len(ACCENTS_TO)
    assert "'( (JR|SR|II|III|IV))+$'" in sql
    assert "'[^A-Z]+', ' ', 'g'" in sql


def test_leie_key_is_a_stable_sha256() -> None:
    assert leie_key("npi||SMITH") == leie_key("npi||SMITH")
    assert re.fullmatch(r"[0-9a-f]{64}", leie_key("x"))


# --------------------------------------------------------------------------
# match_row
# --------------------------------------------------------------------------


def test_exact_name_and_practice_state_is_a_candidate_below_one() -> None:
    [c], ambiguous = match_row(_leie(), [_person()])
    assert not ambiguous
    assert (c.first_name, c.middle_name, c.state) == ("exact", "unknown", "practice")
    assert c.confidence == BASE_CONFIDENCE[("exact", "unknown")]
    assert c.confidence < 1
    assert c.candidate_count == 1
    assert c.detail == {
        "first_name": "exact",
        "middle_name": "unknown",
        "state": "practice",
        "base_confidence": 0.70,
    }


def test_agreeing_middle_initial_scores_highest_and_never_reaches_one() -> None:
    [c], _ = match_row(_leie(middle="M"), [_person(middle="MARIE")])
    assert c.middle_name == "agrees"
    assert c.confidence == MAX_CONFIDENCE
    assert MAX_CONFIDENCE < 1
    assert all(v <= MAX_CONFIDENCE for v in BASE_CONFIDENCE.values())


def test_conflicting_middle_initial_is_not_a_candidate() -> None:
    assert match_row(_leie(middle="X"), [_person(middle="YVES")]) == ([], False)


def test_license_state_counts_when_practice_state_differs() -> None:
    [c], _ = match_row(_leie(state="NJ"), [_person(practice="PA", licenses=("NJ", "PA"))])
    assert c.state == "license"
    [c], _ = match_row(_leie(state="NJ"), [_person(practice="NJ", licenses=("NJ",))])
    assert c.state == "practice_and_license"


def test_other_state_or_other_surname_is_not_a_candidate() -> None:
    assert match_row(_leie(state="CA"), [_person()]) == ([], False)
    assert match_row(_leie(), [_person(last="SAMPLEMATCHES")]) == ([], False)


@pytest.mark.parametrize(
    ("leie_first", "nppes_first", "expected"),
    [
        ("CHRIS", "CHRISTOPHER", "prefix"),
        ("CHRISTOPHER", "CHRIS", "prefix"),
        ("C", "CHRISTOPHER", "initial"),
        ("CH", "CHRISTOPHER", None),  # two letters: neither an initial nor a safe prefix
        ("CHRISTINE", "CHRISTOPHER", None),
        (None, "CHRISTOPHER", None),
    ],
)
def test_first_name_rules(leie_first: str | None, nppes_first: str, expected: str | None) -> None:
    candidates, _ = match_row(_leie(first=leie_first), [_person(first=nppes_first)])
    assert [c.first_name for c in candidates] == ([expected] if expected else [])


def test_surname_normalization_links_punctuation_and_suffix_variants() -> None:
    [c], _ = match_row(_leie(last="O'NEIL-SMITH JR"), [_person(last="ONEIL SMITH")])
    assert c.first_name == "exact"


def test_confidence_is_split_across_same_name_candidates() -> None:
    people = [_person(npi="1990002001"), _person(npi="1990002002", practice="PA", licenses=("NY",))]
    candidates, ambiguous = match_row(_leie(), people)
    assert not ambiguous
    assert [c.candidate_count for c in candidates] == [2, 2]
    assert [c.confidence for c in candidates] == [0.35, 0.35]
    assert [c.person.npi for c in candidates] == ["1990002001", "1990002002"]


def test_duplicate_npi_in_the_block_is_counted_once() -> None:
    candidates, _ = match_row(_leie(), [_person(), _person()])
    assert [c.candidate_count for c in candidates] == [1]


def test_too_many_candidates_writes_none() -> None:
    people = [_person(npi=f"19900030{i:02d}") for i in range(MAX_CANDIDATES_PER_ROW + 1)]
    assert match_row(_leie(), people) == ([], True)
    people = people[:MAX_CANDIDATES_PER_ROW]
    candidates, ambiguous = match_row(_leie(), people)
    assert not ambiguous and len(candidates) == MAX_CANDIDATES_PER_ROW
    assert all(0 < c.confidence < 1 for c in candidates)


def test_summary_keys_for_the_leie_evidence_row() -> None:
    parsed = MatchSummary(nppes_rows_available=True, rows_with_candidates=3).as_parsed()
    assert parsed["name_state_matching_ran"] is True
    assert parsed["rows_without_npi_with_candidates"] == 3


# --------------------------------------------------------------------------
# NPPES weekly incremental
# --------------------------------------------------------------------------

PAGE = """
<a href="NPPES_Data_Dissemination_October_2026_V2.zip">Full</a>
<a href="NPPES_Data_Dissemination_101326_101926_Weekly_V2.zip">wk</a>
<a href="NPPES_Data_Dissemination_102026_102626_Weekly.zip">wk v1</a>
<a href="NPPES_Data_Dissemination_102026_102626_Weekly_V2.zip">wk v2</a>
<a href="NPPES_Data_Dissemination_100626_101226_Weekly_V2.zip">older</a>
<a href="NPPES_Deactivated_NPI_Report_101426.zip">deact</a>
"""


def test_weekly_link_takes_the_newest_week_and_prefers_v2() -> None:
    assert find_weekly_link(PAGE) == (
        "https://download.cms.gov/nppes/NPPES_Data_Dissemination_102026_102626_Weekly_V2.zip"
    )


def test_weekly_link_absent_and_year_rollover() -> None:
    assert find_weekly_link('<a href="NPPES_Data_Dissemination_October_2026_V2.zip">') is None
    page = (
        '<a href="NPPES_Data_Dissemination_122826_010327_Weekly_V2.zip">'
        '<a href="NPPES_Data_Dissemination_122126_122726_Weekly_V2.zip">'
    )
    link = find_weekly_link(page)
    assert link is not None and link.endswith("122826_010327_Weekly_V2.zip")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=None, storage_path=str(tmp_path / "storage"), work_dir=tmp_path / "work"
    )


def test_weekly_link_off_the_allowlist_is_refused(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = NppesWeeklyConnector(settings)
    monkeypatch.setattr(
        connector,
        "fetch_text",
        lambda url, **_: (
            '<a href="https://evil.example/NPPES_Data_Dissemination_102026_102626_Weekly_V2.zip">'
        ),
    )
    with pytest.raises(ConnectorError):
        connector.discover_download_url()


def test_weekly_page_without_a_weekly_link_fails_loudly(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = NppesWeeklyConnector(settings)
    monkeypatch.setattr(connector, "fetch_text", lambda url, **_: "<html></html>")
    with pytest.raises(ConnectorError, match="Weekly"):
        connector.discover_download_url()


def test_weekly_parses_the_same_layout_as_the_replicate(tmp_path: Path, settings: Settings) -> None:
    path = write_nppes_zip(tmp_path / "wk.zip", [INDIVIDUAL, nppes_row("1003000126")])
    rows = list(NppesWeeklyConnector(settings).parse(path))
    assert [r["npi"] for r in rows] == ["1598027682", "1003000126"]
    assert rows[0]["last_name"] == "PEÑA"


def test_weekly_connector_is_registered_before_leie_and_never_floors_rows() -> None:
    keys = connector_keys()
    assert CONNECTORS["nppes_weekly"] is NppesWeeklyConnector
    assert keys.index("nppes") < keys.index("oig_leie")
    assert keys.index("nppes_weekly") < keys.index("oig_leie")
    assert NppesWeeklyConnector.cadence == "weekly"
    assert NppesWeeklyConnector.min_rows_fraction == 0.0
    assert NppesWeeklyConnector.key != "nppes"


def test_weekly_upsert_never_moves_a_row_backwards() -> None:
    assert "excluded.last_update_date >= nppes_providers.last_update_date" in _WEEKLY_UPSERT
    assert "absent_since = null" in _WEEKLY_UPSERT
    assert "update nppes_providers p" not in _WEEKLY_UPSERT  # no absent marking
