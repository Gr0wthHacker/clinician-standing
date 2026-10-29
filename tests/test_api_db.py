"""PostgresStore against a real schema, with synthetic rows.

Marked ``database``: CI's database job applies every migration and seed, then
runs these. The seed is invented (SAMPLE / TESTCASE, NPIs starting 1990001) and
lives in one transaction that is always rolled back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest

from clinician_standing.api import service
from clinician_standing.api.models import CheckRequest
from clinician_standing.api.store import PostgresStore
from conftest import database_url

pytestmark = pytest.mark.database

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

ALPHA = "1990001012"
BRAVO = "1990001020"
CHARLIE = "1990001038"

DAC_EV = "aaaaaaaa-0000-4000-8000-00000000d001"
LEIE_EV = "aaaaaaaa-0000-4000-8000-00000000d002"
NURSYS_EV = "aaaaaaaa-0000-4000-8000-00000000d003"
PRACTICE_MN = "aaaaaaaa-0000-4000-8000-00000000d0a1"
PRACTICE_WI = "aaaaaaaa-0000-4000-8000-00000000d0a2"

_EVIDENCE = """
insert into evidence (id, source_key, fetched_at, payload_ref, payload_sha256, parsed,
                      match_keys, freshness_expires_at)
values (%(id)s, %(key)s, %(fetched)s, %(ref)s, %(sha)s, %(parsed)s, %(mk)s, %(expires)s)
"""


def _seed(cur) -> None:
    for ev in (
        {
            "id": DAC_EV,
            "key": "cms_dac",
            "fetched": datetime(2026, 10, 2, 4, 12, tzinfo=UTC),
            "ref": "synthetic/cms_dac.csv",
            "sha": "d1" * 32,
            "parsed": "{}",
            "mk": '{"npi": "exact"}',
            "expires": datetime(2026, 11, 16, 4, 12, tzinfo=UTC),
        },
        {
            "id": LEIE_EV,
            "key": "oig_leie",
            "fetched": datetime(2026, 8, 1, 2, 5, tzinfo=UTC),
            "ref": "synthetic/oig_leie.csv",
            "sha": "d2" * 32,
            "parsed": (
                '{"rows_total": 100, "rows_with_npi": 10, "name_dob_matching_enabled": false}'
            ),
            "mk": '{"npi": "exact"}',
            "expires": datetime(2026, 9, 15, 2, 5, tzinfo=UTC),
        },
        {
            "id": NURSYS_EV,
            "key": "nursys",
            "fetched": datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
            "ref": "synthetic/nursys.json",
            "sha": "d3" * 32,
            "parsed": "{}",
            "mk": '{"ncsbn_id": 1, "method": "nursys_ncsbn", "has_discipline": false}',
            "expires": datetime(2027, 1, 8, 12, 0, tzinfo=UTC),
        },
    ):
        cur.execute(_EVIDENCE, ev)

    for pid, pac, state in ((PRACTICE_MN, "9900001001", "MN"), (PRACTICE_WI, "9900001002", "WI")):
        cur.execute(
            "insert into practices (id, org_pac_id, legal_name, state) "
            "values (%s, %s, 'SAMPLE TEST PRACTICE', %s)",
            (pid, pac, state),
        )
    for npi, first, kind in ((ALPHA, "ALPHA", "physician"), (BRAVO, "BRAVO", "physician")):
        cur.execute(
            "insert into clinicians (npi, first_name, last_name, clinician_type) "
            "values (%s, %s, 'SAMPLE', %s)",
            (npi, first, kind),
        )
    cur.execute(
        "insert into clinicians (npi, first_name, last_name, clinician_type) "
        "values (%s, 'CHARLIE', 'SAMPLE', 'np')",
        (CHARLIE,),
    )
    for npi, pid, end in (
        (ALPHA, PRACTICE_MN, None),
        (BRAVO, PRACTICE_MN, None),
        (BRAVO, PRACTICE_WI, None),
        (ALPHA, PRACTICE_WI, date(2025, 1, 31)),  # ended: must not count toward WI
    ):
        cur.execute(
            "insert into affiliations (clinician_id, practice_id, end_date) "
            "select id, %s, %s from clinicians where npi = %s",
            (pid, end, npi),
        )
    cur.execute(
        "insert into sanctions (clinician_id, source, action_type, action_date, description, "
        "match_confidence, evidence_id) "
        "select id, 'leie', '1128b4', date '2025-03-15', 'SYNTHETIC TEST EXCLUSION', 1.0, %s "
        "from clinicians where npi = %s",
        (LEIE_EV, BRAVO),
    )
    cur.execute(
        "insert into licenses (clinician_id, state, license_type, license_number, status, "
        "issue_date, expiry_date, evidence_id, verified_at) "
        "select id, 'WI', 'APRN', 'TEST-0001', 'active', date '2018-01-15', date '2027-02-28', "
        "%s, %s from clinicians where npi = %s",
        (NURSYS_EV, datetime(2026, 10, 10, 12, 0, tzinfo=UTC), CHARLIE),
    )


@pytest.fixture
def store() -> Iterator[PostgresStore]:
    import psycopg

    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    conn = psycopg.connect(url, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("begin")
            _seed(cur)

        @contextmanager
        def factory() -> Iterator[psycopg.Connection]:
            yield conn

        yield PostgresStore(connection_factory=factory)
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("rollback")
        finally:
            conn.close()


def test_sources_read_from_registry(store: PostgresStore) -> None:
    block = service.build_sources_block(store.list_sources(), NOW)
    checked = {s.key for s in block.checked}
    assert {"cms_dac", "oig_leie", "nursys"} <= checked
    not_checked = {s.key for s in block.not_checked}
    assert {"sam_gov", "nppes", "state_ca"} <= not_checked
    leie = next(s for s in block.checked if s.key == "oig_leie")
    assert leie.stale is True


def test_npi_lookup_with_open_exclusion(store: PostgresStore) -> None:
    resp = service.check(store, CheckRequest(npi=BRAVO), now=NOW)
    assert resp.result == "found"
    c = resp.clinicians[0]
    assert c.identity.practice_states == ["MN", "WI"]
    assert c.exclusions.status == "open_exclusion_found"
    [match] = c.exclusions.matches
    assert match.source_key == "oig_leie"
    assert match.action_date == date(2025, 3, 15)
    assert match.match_confidence == 1.0


def test_clean_npi(store: PostgresStore) -> None:
    c = service.check(store, CheckRequest(npi=ALPHA), now=NOW).clinicians[0]
    assert c.identity.practice_states == ["MN"]
    assert c.exclusions.status == "no_npi_match"
    assert "90 of the 100 records" in c.exclusions.note
    assert c.licenses.coverage == "no_records_found"


def test_license_record_and_discipline_flag(store: PostgresStore) -> None:
    c = service.check(store, CheckRequest(npi=CHARLIE), now=NOW).clinicians[0]
    [lic] = c.licenses.records
    assert (lic.state, lic.status, lic.source_key) == ("WI", "active", "nursys")
    assert lic.discipline_reported is False


def test_name_state_uses_active_affiliations_and_licenses(store: PostgresStore) -> None:
    mn = service.check(store, CheckRequest(last_name="sample", state="MN"), now=NOW)
    assert [c.identity.npi for c in mn.clinicians] == [ALPHA, BRAVO]
    wi = service.check(store, CheckRequest(last_name="SAMPLE", state="WI"), now=NOW)
    # ALPHA's WI affiliation ended; CHARLIE is tied to WI by license only.
    assert [c.identity.npi for c in wi.clinicians] == [BRAVO, CHARLIE]
    one = service.check(
        store, CheckRequest(last_name="SAMPLE", first_name="charlie", state="WI"), now=NOW
    )
    assert one.result == "found"


def test_unknown_npi(store: PostgresStore) -> None:
    resp = service.check(store, CheckRequest(npi="1990001053"), now=NOW)
    assert resp.result == "not_found"
