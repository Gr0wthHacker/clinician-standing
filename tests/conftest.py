"""Shared fixtures.

Every test in this suite must run with no network and no database. Anything
that needs either is marked `network` or `database` and deselected in CI.

The ingest package itself is written by a separate workstream, so the tests
here probe for it rather than assume it. `require(...)` returns a skip marker
when a module or attribute is not there yet, which keeps CI green while the
package lands and turns the test on automatically the moment it exists.
"""

from __future__ import annotations

import csv
import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

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
# Probing helpers
# --------------------------------------------------------------------------
def try_import(name: str) -> ModuleType | None:
    """Import a module, returning None if it does not exist yet."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def find_attr(module: ModuleType | None, *names: str) -> Any | None:
    """Return the first attribute in `names` present on `module`, else None."""
    if module is None:
        return None
    for name in names:
        attr = getattr(module, name, None)
        if attr is not None:
            return attr
    return None


def require(module_name: str, *attrs: str) -> pytest.MarkDecorator:
    """Skip marker for a module (and optionally an attribute) not yet written.

    Usage::

        @require("clinician_standing.config", "validate")
        def test_something(): ...
    """
    module = try_import(module_name)
    if module is None:
        return pytest.mark.skip(reason=f"awaiting {module_name}")
    if attrs and find_attr(module, *attrs) is None:
        wanted = " or ".join(attrs)
        return pytest.mark.skip(reason=f"awaiting {module_name}.{wanted}")
    return pytest.mark.skipif(False, reason="module present")


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
