"""The sample roster, end to end.

``tests/fixtures/sample`` holds two monthly snapshots of each Tier 1 bulk file,
shaped exactly like the CMS and OIG files the connectors parse, for an invented
five-clinician roster across two groups. Nothing in them is real: names are
placeholders and the NPIs are generated with a valid check digit by
``scripts/make_sample_fixtures.py``.

The hermetic tests check the fixtures parse the way the real files do. The
``database`` test runs all three connectors against a scratch database created
for the test and dropped afterwards (the connectors commit their own
transactions, so a rollback cannot clean up after them), as ``app_ingest`` so the
row-level security in 0008/0011 applies:

* month 1 loads the roster, Medicare enrollments and one NPI exclusion;
* month 1 again reports zero new and zero changed rows;
* month 2 closes an affiliation the clinician left, keeps open the one whose
  clinician left the file entirely, moves a revalidation date and records a
  new exclusion.
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from clinician_standing.config import Settings
from clinician_standing.connectors.cms_dac import CmsDacConnector
from clinician_standing.connectors.cms_revalidation import CmsRevalidationConnector
from clinician_standing.connectors.oig_leie import OigLeieConnector
from clinician_standing.evidence import _dumps
from conftest import FIXTURE_DIR, database_url

SAMPLE = FIXTURE_DIR / "sample"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from make_sample_fixtures import GROUP_A, GROUP_B, NPI, npi_with_check_digit  # noqa: E402

CONNECTORS = (
    ("cms_dac", CmsDacConnector),
    ("cms_revalidation", CmsRevalidationConnector),
    ("oig_leie", OigLeieConnector),
)


def _settings(tmp_path: Path, url: str = "postgresql://unused@127.0.0.1/unused") -> Settings:
    return Settings(
        database_url=url,
        storage_path=str(tmp_path / "storage"),
        work_dir=tmp_path / "work",
    )


# --------------------------------------------------------------------------
# Hermetic
# --------------------------------------------------------------------------
def test_npi_check_digit_matches_the_published_example():
    # CMS's worked example: 123456789 -> check digit 3.
    assert npi_with_check_digit("123456789") == "1234567893"


@pytest.mark.parametrize("npi", sorted(NPI.values()))
def test_sample_npis_carry_valid_check_digits(npi: str):
    assert npi_with_check_digit(npi[:9]) == npi


def test_committed_fixtures_match_the_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import make_sample_fixtures as gen

    monkeypatch.setattr(gen, "OUT", tmp_path)
    gen.main()
    for path in sorted(tmp_path.rglob("*.csv")):
        committed = SAMPLE / path.relative_to(tmp_path)
        assert committed.read_bytes() == path.read_bytes(), (
            f"{committed} is stale; run python scripts/make_sample_fixtures.py"
        )


@pytest.mark.parametrize(
    ("key", "cls", "v1_rows", "v2_rows"),
    [
        ("cms_dac", CmsDacConnector, 7, 5),
        ("cms_revalidation", CmsRevalidationConnector, 7, 5),
        ("oig_leie", OigLeieConnector, 5, 6),
    ],
)
def test_sample_files_parse(tmp_path: Path, key: str, cls: type, v1_rows: int, v2_rows: int):
    connector = cls(_settings(tmp_path))
    assert len(list(connector.parse(SAMPLE / "v1" / f"{key}.csv"))) == v1_rows
    assert len(list(connector.parse(SAMPLE / "v2" / f"{key}.csv"))) == v2_rows


def test_dac_sample_dedupes_locations(tmp_path: Path):
    connector = CmsDacConnector(_settings(tmp_path))
    rows = list(connector.parse(SAMPLE / "v1" / "cms_dac.csv"))
    # GROUP_A has two locations, so its five clinicians appear on ten lines.
    assert connector.rows_before_dedupe == 12
    assert {(r["npi"], r["org_pac_id"]) for r in rows} == {
        (NPI["alpha"], GROUP_A),
        (NPI["bravo"], GROUP_A),
        (NPI["charlie"], GROUP_A),
        (NPI["delta"], GROUP_A),
        (NPI["echo"], GROUP_A),
        (NPI["alpha"], GROUP_B),
        (NPI["charlie"], GROUP_B),
    }


def test_leie_sample_keeps_latin1_names(tmp_path: Path):
    rows = list(OigLeieConnector(_settings(tmp_path)).parse(SAMPLE / "v1" / "oig_leie.csv"))
    assert any(r["last_name"] == "PE\u00d1A\u00a0SAMPLE" for r in rows)
    assert sum(1 for r in rows if r["npi"]) == 2


def test_evidence_jsonb_accepts_dates():
    # The LEIE per-match record carries dates; plain json.dumps raised on them
    # and every run that matched a roster NPI failed before writing a sanction.
    assert _dumps({"exclusion_date": date(2025, 1, 15)}) == '{"exclusion_date": "2025-01-15"}'


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def _with_db(url: str, dbname: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    if user:
        netloc = f"{user}:{password}@{netloc}" if password else f"{user}@{netloc}"
    elif "@" in parts.netloc:
        netloc = parts.netloc
    return urlunsplit((parts.scheme, netloc, f"/{dbname}", parts.query, parts.fragment))


@pytest.fixture
def scratch_db() -> Iterator[tuple[str, str]]:
    """A freshly migrated and seeded database; yields (admin_url, ingest_url)."""
    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    import psycopg

    name = f"cs_sample_{secrets.token_hex(4)}"
    password = secrets.token_hex(16)
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    admin_url = _with_db(url, name)
    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            scripts = [ROOT / "db" / "ci" / "bootstrap.sql"]
            scripts += sorted((ROOT / "db" / "migrations").glob("0*.sql"))
            scripts += sorted((ROOT / "db" / "seeds").glob("*.sql"))
            for script in scripts:
                conn.execute(script.read_text(encoding="utf-8").encode("utf-8"))
            # app_ingest is cluster-wide; TEST_DATABASE_URL is documented as a
            # throwaway cluster, so giving it a random password here is safe.
            conn.execute(f"alter role app_ingest password '{password}'")
        yield admin_url, _with_db(url, name, "app_ingest", password)
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


def _run_month(
    month: str, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> dict[str, tuple[str, int, int, int]]:
    out = {}
    for key, cls in CONNECTORS:
        monkeypatch.setenv(f"LOCAL_SOURCE_{key.upper()}", str(SAMPLE / month / f"{key}.csv"))
        result = cls(settings).run()
        assert result.ok, f"{key} {month}: {result.error}"
        out[key] = (result.status, result.rows_in, result.rows_new, result.rows_changed)
    return out


@pytest.mark.database
def test_sample_roster_end_to_end(
    scratch_db: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import psycopg

    admin_url, ingest_url = scratch_db
    settings = _settings(tmp_path, ingest_url)

    first = _run_month("v1", settings, monkeypatch)
    assert first == {
        "cms_dac": ("ok", 7, 7, 0),
        "cms_revalidation": ("ok", 7, 7, 0),
        "oig_leie": ("ok", 5, 5, 0),
    }
    # Same files again: the Phase 2 acceptance criterion.
    again = _run_month("v1", settings, monkeypatch)
    assert {k: v[2:] for k, v in again.items()} == dict.fromkeys(again, (0, 0))

    second = _run_month("v2", settings, monkeypatch)
    assert second["oig_leie"][2] == 1

    with psycopg.connect(admin_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select c.npi, p.org_pac_id, a.end_date is not null
              from affiliations a
              join clinicians c on c.id = a.clinician_id
              join practices p on p.id = a.practice_id
            """
        )
        ended = {(npi, pac): closed for npi, pac, closed in cur.fetchall()}
        assert len(ended) == 7
        assert ended[(NPI["charlie"], GROUP_B)] is True  # left one of two groups
        assert ended[(NPI["delta"], GROUP_A)] is False  # left the file: kept open
        assert sum(ended.values()) == 1

        cur.execute(
            """
            select e.revalidation_due from enrollments e
              join clinicians c on c.id = e.clinician_id
              join practices p on p.id = e.practice_id
             where c.npi = %s and p.org_pac_id = %s
            """,
            (NPI["bravo"], GROUP_A),
        )
        assert cur.fetchone() == (date(2028, 1, 31),)

        cur.execute(
            """
            select c.npi, s.action_type, s.match_confidence, s.evidence_id is not null
              from sanctions s join clinicians c on c.id = s.clinician_id
             order by c.npi
            """
        )
        sanctions = cur.fetchall()
        assert [(n, t, ev) for n, t, _, ev in sanctions] == [
            (NPI["charlie"], "1128b4", True),
            (NPI["echo"], "1128b7", True),
        ]
        assert all(float(conf) == 1.0 for _, _, conf, _ in sanctions)

        cur.execute("select count(*) from source_runs where status = 'ok'")
        assert cur.fetchone() == (9,)
