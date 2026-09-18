"""Shared fixtures.

Every test in this suite must run with no network and no database. Anything
that needs either is marked `network` or `database` and deselected in CI.

THE PACKAGE IS IMPORTED DIRECTLY. This file used to carry `try_import`,
`find_attr` and `require`, which turned a failed import into a pytest skip so
that the suite could be written before the package existed. That scaffolding
outlived its purpose and became a hazard: once `clinician_standing` shipped,
any refactor that broke the package -- a renamed module, a syntax error, a
circular import, a missing dependency -- turned every test that touched it into
a skip, and CI stayed green while the thing under test was gone. A skip is not
a pass. Tests import what they test; if the import fails, the suite fails.

The one remaining conditional is the `database` marker, which is a genuine
environment fact rather than a statement about whether the code exists.
"""

from __future__ import annotations

import csv
import importlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# Environment variables the ingest layer reads. Cleared before every test so a
# developer's shell or a CI runner cannot make a test pass by accident.
MANAGED_ENV_VARS = (
    "DATABASE_URL",
    "STORAGE_PATH",
    "LOG_LEVEL",
    "INGEST_USE_CACHE",
    "INGEST_SOURCES",
    "HTTP_TIMEOUT_SECONDS",
    "HTTP_USER_AGENT",
    "NURSYS_API_KEY",
    "FSMB_API_KEY",
)


# --------------------------------------------------------------------------
# require() -- retained as a call-site shim, WITHOUT the skip.
#
# This used to return `pytest.mark.skip` when a module or attribute was
# missing. Keeping the name but not the behaviour is deliberate: the import now
# happens for real, so a package that will not import raises ImportError at
# collection time and the suite goes red, and a missing attribute raises
# AttributeError. Neither is a skip. New tests should import what they test
# directly and not call this at all.
# --------------------------------------------------------------------------
def require(module_name: str, *attrs: str) -> pytest.MarkDecorator:
    """Assert a module and its attributes exist, and return a no-op marker.

    Raises:
        ImportError: If the module does not import. Not caught: a broken
            package must fail the suite, not silently disable it.
        AttributeError: If none of ``attrs`` is present on the module.
    """
    module = importlib.import_module(module_name)
    if attrs and not any(hasattr(module, name) for name in attrs):
        raise AttributeError(f"{module_name} has none of {attrs}")
    return pytest.mark.skipif(False, reason="module present")


# --------------------------------------------------------------------------
# Database-backed tests
#
# TEST_DATABASE_URL, not DATABASE_URL: the latter is cleared by clean_env for
# every test, on purpose, so that nothing can pass by picking up a developer's
# or a runner's real database by accident.
# --------------------------------------------------------------------------
def database_url() -> str | None:
    """Connection URI for the `database`-marked tests, or None if unset."""
    value = os.environ.get("TEST_DATABASE_URL", "").strip()
    return value or None


@pytest.fixture
def db_connection() -> Iterator[object]:
    """A live connection for a `database`-marked test, always rolled back.

    Skips only when TEST_DATABASE_URL is unset -- an environment fact. A driver
    that will not import or a database that will not accept the connection is an
    error, not a skip.

    The rollback is in a `finally` on purpose. A test that fails partway leaves
    its rows behind otherwise, and the next run fails on a unique violation
    instead of on the thing that actually broke -- which turns one red test into
    a suite that stays red for the wrong reason.
    """
    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    import psycopg

    conn = psycopg.connect(url)
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every variable the ingest layer reads, for every test."""
    for var in MANAGED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """A minimally complete environment: DATABASE_URL plus a writable storage dir."""
    storage = tmp_path / "storage"
    storage.mkdir()
    env = {
        "DATABASE_URL": "postgresql://postgres:pw@127.0.0.1:5432/postgres",
        "STORAGE_PATH": str(storage),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


# --------------------------------------------------------------------------
# Encoding fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def latin1_csv_path() -> Path:
    """Committed sample carrying the 0xa0 byte that broke LEIE and revalidation."""
    path = FIXTURE_DIR / "leie_latin1_sample.csv"
    assert path.exists(), f"missing fixture: {path}"
    return path


@pytest.fixture
def latin1_csv_bytes(latin1_csv_path: Path) -> bytes:
    return latin1_csv_path.read_bytes()


# --------------------------------------------------------------------------
# Dedupe fixtures
# --------------------------------------------------------------------------
# The CMS Doctors and Clinicians file carries one row per clinician PER
# PRACTICE LOCATION. Counting it raw overstates the roster: 3.39M rows is not
# 3.39M clinician-practice pairs. The identity of a row is (NPI, org_pac_id);
# adr_ln_1 / city / zip / phone vary within a pair and must not be part of the key.
DAC_DUPLICATE_ROWS: list[dict[str, str]] = [
    # Same clinician, same group, two locations -> one pair.
    {
        "NPI": "1234567893",
        "Ind_PAC_ID": "4183futures",
        "org_pac_id": "0042000001",
        "Provider Last Name": "SMITH",
        "adr_ln_1": "100 MAIN ST",
        "City/Town": "AUSTIN",
        "ZIP Code": "78701",
        "Telehlth": "Y",
    },
    {
        "NPI": "1234567893",
        "Ind_PAC_ID": "4183futures",
        "org_pac_id": "0042000001",
        "Provider Last Name": "SMITH",
        "adr_ln_1": "220 SECOND AVE",
        "City/Town": "ROUND ROCK",
        "ZIP Code": "78664",
        "Telehlth": "Y",
    },
    # Third location for the same pair.
    {
        "NPI": "1234567893",
        "Ind_PAC_ID": "4183futures",
        "org_pac_id": "0042000001",
        "Provider Last Name": "SMITH",
        "adr_ln_1": "9 CLINIC RD",
        "City/Town": "PFLUGERVILLE",
        "ZIP Code": "78660",
        "Telehlth": "N",
    },
    # Same clinician, DIFFERENT group -> a distinct pair, must survive.
    {
        "NPI": "1234567893",
        "Ind_PAC_ID": "4183futures",
        "org_pac_id": "0042000002",
        "Provider Last Name": "SMITH",
        "adr_ln_1": "500 GROUP WAY",
        "City/Town": "AUSTIN",
        "ZIP Code": "78702",
        "Telehlth": "N",
    },
    # Different clinician, same group -> a distinct pair, must survive.
    {
        "NPI": "1987654320",
        "Ind_PAC_ID": "9930000777",
        "org_pac_id": "0042000001",
        "Provider Last Name": "PENA",
        "adr_ln_1": "100 MAIN ST",
        "City/Town": "AUSTIN",
        "ZIP Code": "78701",
        "Telehlth": "Y",
    },
    # Exact duplicate line: the file contains these too.
    {
        "NPI": "1987654320",
        "Ind_PAC_ID": "9930000777",
        "org_pac_id": "0042000001",
        "Provider Last Name": "PENA",
        "adr_ln_1": "100 MAIN ST",
        "City/Town": "AUSTIN",
        "ZIP Code": "78701",
        "Telehlth": "Y",
    },
]

# (NPI, org_pac_id) pairs that must remain after deduplication.
DAC_EXPECTED_PAIRS: set[tuple[str, str]] = {
    ("1234567893", "0042000001"),
    ("1234567893", "0042000002"),
    ("1987654320", "0042000001"),
}


@pytest.fixture
def dac_rows() -> list[dict[str, str]]:
    """Six raw DAC-shaped rows collapsing to three (NPI, org_pac_id) pairs."""
    return [dict(row) for row in DAC_DUPLICATE_ROWS]


@pytest.fixture
def expected_pairs() -> set[tuple[str, str]]:
    return set(DAC_EXPECTED_PAIRS)


@pytest.fixture
def dac_csv_path(tmp_path: Path, dac_rows: list[dict[str, str]]) -> Path:
    """The same rows written out as a CSV, for parser-level tests."""
    path = tmp_path / "dac_sample.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dac_rows[0].keys()))
        writer.writeheader()
        writer.writerows(dac_rows)
    return path
