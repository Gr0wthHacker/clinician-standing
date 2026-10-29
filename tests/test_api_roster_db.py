"""PostgresRosterStore against the real schema, running as app_roster_api.

Marked ``database``. Each test runs in one transaction that is rolled back, with
``SET LOCAL ROLE app_roster_api`` so the grants and policies from
``0019_roster_intake.sql`` are what is exercised, not the superuser's reach.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from clinician_standing.api.models import RosterSubmission
from clinician_standing.api.roster_store import PostgresRosterStore, RosterEntryClosed
from conftest import database_url

pytestmark = pytest.mark.database

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _submission(**overrides: Any) -> RosterSubmission:
    body: dict[str, Any] = {
        "source_system": "placerail",
        "external_id": "db-test-placement-1",
        "clinician": {"first_name": "Alpha", "last_name": "Sample", "npi": "1990001012"},
        "licenses": [{"state": "MN", "license_type": "RN"}],
        "employer": {"name": "Sample Test Clinic"},
    }
    body.update(overrides)
    return RosterSubmission.model_validate(body)


@pytest.fixture
def conn() -> Iterator[Any]:
    import psycopg

    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    connection = psycopg.connect(url, autocommit=True)
    try:
        with connection.cursor() as cur:
            cur.execute("begin")
            cur.execute("set local role app_roster_api")
        yield connection
    finally:
        try:
            with connection.cursor() as cur:
                cur.execute("rollback")
        finally:
            connection.close()


@pytest.fixture
def store(conn: Any) -> PostgresRosterStore:
    @contextmanager
    def factory() -> Iterator[Any]:
        yield conn

    return PostgresRosterStore(connection_factory=factory)


def test_create_unchanged_updated(store: PostgresRosterStore) -> None:
    first = store.upsert(_submission(), "abc123", NOW)
    assert first.outcome == "created"
    assert first.review_status == "pending"
    same = store.upsert(_submission(), "abc123", NOW)
    assert (same.outcome, same.id) == ("unchanged", first.id)
    changed = store.upsert(_submission(employment_status="ended"), "abc123", NOW)
    assert (changed.outcome, changed.id) == ("updated", first.id)
    assert changed.updated_at == NOW


def test_row_contents(store: PostgresRosterStore, conn: Any) -> None:
    store.upsert(_submission(states=["wi"]), "abc123", NOW)
    with conn.cursor() as cur:
        cur.execute(
            "select last_name, npi, states, licenses, employer_name, review_status "
            "from roster_intake where external_id = 'db-test-placement-1'"
        )
        row = cur.fetchone()
    assert row[0] == "SAMPLE"
    assert row[1] == "1990001012"
    assert row[2] == ["MN", "WI"]
    assert row[3] == [
        {"state": "MN", "license_type": "RN", "license_number": None, "expires_on": None}
    ]
    assert row[4] == "Sample Test Clinic"
    assert row[5] == "pending"


def test_role_cannot_reach_other_tables(conn: Any) -> None:
    import psycopg

    with conn.cursor() as cur:
        cur.execute("savepoint s")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select 1 from clinicians limit 1")
        cur.execute("rollback to savepoint s")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from roster_intake")
        cur.execute("rollback to savepoint s")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("update roster_intake set review_status = 'matched'")
        cur.execute("rollback to savepoint s")


def test_closed_row_is_reported(store: PostgresRosterStore, conn: Any) -> None:
    store.upsert(_submission(), "abc123", NOW)
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute(
            "update roster_intake set deleted_at = now() where external_id = 'db-test-placement-1'"
        )
        cur.execute("set local role app_roster_api")
    with pytest.raises(RosterEntryClosed):
        store.upsert(_submission(employment_status="ended"), "abc123", NOW)
