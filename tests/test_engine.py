"""The obligations engine (PRD section 7, build phase 4).

Two kinds of test live here.

The pure ones exercise date arithmetic, severity assignment and priority
ordering against an in-memory :class:`~clinician_standing.engine.Roster`. They
need nothing but the module and run in CI.

The rest are marked ``database`` and are deselected in CI (see
``pyproject.toml``). They want a Postgres with ``db/migrations`` applied and
``DATABASE_URL`` (or ``TEST_DATABASE_URL``) pointing at it::

    initdb -D /tmp/pg && pg_ctl -D /tmp/pg -o '-p 55433' start
    createdb -p 55433 csdb
    for f in db/migrations/*.sql; do psql -p 55433 -d csdb -f "$f"; done
    TEST_DATABASE_URL=postgresql://localhost:55433/csdb pytest -m database

They exist because the one thing that cannot be proven without a real server is
the thing most likely to be wrong: whether the ``ON CONFLICT`` clause actually
infers ``ux_obligations_open_duty``. Get that wrong and every nightly run
duplicates every obligation, silently.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from conftest import require

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing import engine as eng
except ImportError:  # pragma: no cover
    eng = None  # type: ignore[assignment]

needs_engine = require("clinician_standing.engine", "run")

MIGRATIONS = Path(__file__).resolve().parents[1] / "db" / "migrations"

#: Fixed run date. Every expected value below is derived from it, never from
#: ``today()``: a calendar test that changes its own answer overnight is not a
#: test.
AS_OF = date(2026, 9, 18)
GENERATED_AT = datetime(2026, 9, 19, 2, 0, tzinfo=UTC)

PRACTICE_TX = UUID("aaaaaaaa-0000-4000-8000-000000000001")
PRACTICE_CA = UUID("aaaaaaaa-0000-4000-8000-000000000002")
EVIDENCE_ID = UUID("eeeeeeee-0000-4000-8000-000000000001")

#: 20 clinicians: 12 physicians affiliated to the Texas practice, 8 nurse
#: practitioners to the California one. Ids are derived from the index so a
#: failure names a row you can go and look at.
CLINICIAN_COUNT = 20
TX_COUNT = 12


def clinician_id(index: int) -> UUID:
    return UUID(f"cccccccc-0000-4000-8000-{index:012d}")


def is_tx(index: int) -> bool:
    return index < TX_COUNT


#: Index 0 carries an expired Texas licence -- the PRD 7 critical case.
EXPIRED_INDEX = 0
#: Index 11 carries a licence with an issue date and no expiry date, so its due
#: date is computed from ``renewal_cycle_months`` and a new version of that rule
#: moves it. This is the row the version-bump test watches.
NO_EXPIRY_INDEX = 11
NO_EXPIRY_ISSUE = date(2025, 3, 15)
#: Index 19 never bills, so a lapse there is not critical.
NON_BILLING_INDEX = 19


# ===========================================================================
# Seeding
# ===========================================================================
def _license_expiry(index: int) -> date | None:
    """Spread licence expiries one per month across the next 12 months.

    Texas physicians take months 1-10 and California nurses months 5-12, so
    between them every one of the next twelve months carries at least one
    renewal. That is what makes "a correct 12-month obligation calendar" a
    checkable claim rather than a vibe. Two indices sit outside the calendar on
    purpose: one licence is already expired and one has no expiry date at all.
    """
    if index == EXPIRED_INDEX:
        return AS_OF - timedelta(days=40)
    if index == NO_EXPIRY_INDEX:
        return None
    offset = index if is_tx(index) else index - 7
    return eng.month_end(eng.add_months(AS_OF, offset))


def seed_roster(conn) -> None:
    """Write two practices, 20 clinicians, their licences and enrolments.

    Everything is inserted with explicit ids so a test can assert about a named
    row. Credential rows carry the one seeded ``evidence`` row, because
    ``licenses.evidence_id`` is NOT NULL by design (0003_credentials.sql).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into evidence (id, source_key, fetched_at, payload_ref,
                                  payload_sha256, freshness_expires_at)
            values (%s, 'cms_dac', %s, 'seed/test', %s, %s)
            on conflict (id) do nothing
            """,
            (EVIDENCE_ID, GENERATED_AT, "0" * 64, GENERATED_AT + timedelta(days=30)),
        )
        for practice_id, name, tier, state in (
            (PRACTICE_TX, "Northside Medical Group", "complete", "TX"),
            (PRACTICE_CA, "Bayview Clinic Partners", "essential", "CA"),
        ):
            cur.execute(
                """
                insert into practices (id, legal_name, tier, client_status, state)
                values (%s, %s, %s, 'active', %s)
                on conflict (id) do nothing
                """,
                (practice_id, name, tier, state),
            )

        for index in range(CLINICIAN_COUNT):
            cid = clinician_id(index)
            texas = is_tx(index)
            cur.execute(
                """
                insert into clinicians (id, npi, first_name, last_name, credential,
                                        clinician_type)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (id) do nothing
                """,
                (
                    cid,
                    f"1{index:09d}",
                    "Test",
                    f"Clinician{index:02d}",
                    "MD" if texas else "NP",
                    "physician" if texas else "np",
                ),
            )
            cur.execute(
                """
                insert into affiliations (clinician_id, practice_id, start_date,
                                          employment_type, is_billing)
                values (%s, %s, %s, 'employed', %s)
                on conflict (clinician_id, practice_id, start_date) do nothing
                """,
                (
                    cid,
                    PRACTICE_TX if texas else PRACTICE_CA,
                    date(2024, 1, 1),
                    index != NON_BILLING_INDEX,
                ),
            )
            expiry = _license_expiry(index)
            cur.execute(
                """
                insert into licenses (clinician_id, state, license_type, license_number,
                                      status, issue_date, expiry_date, evidence_id,
                                      verified_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (clinician_id, state, license_type, license_number)
                do nothing
                """,
                (
                    cid,
                    "TX" if texas else "CA",
                    "MD" if texas else "APRN",
                    f"L{index:05d}",
                    "expired" if index == EXPIRED_INDEX else "active",
                    NO_EXPIRY_ISSUE if index == NO_EXPIRY_INDEX else date(2022, 1, 3),
                    expiry,
                    EVIDENCE_ID,
                    GENERATED_AT,
                ),
            )
            cur.execute(
                """
                insert into enrollments (clinician_id, practice_id, payer, status,
                                         effective_date, revalidation_due, par_status,
                                         evidence_id, verified_at)
                values (%s, %s, 'medicare', 'approved', %s, %s, 'par', %s, %s)
                """,
                (
                    cid,
                    PRACTICE_TX if texas else PRACTICE_CA,
                    date(2023, 4, 1),
                    date(2028, 4, 1) + timedelta(days=index),
                    EVIDENCE_ID,
                    GENERATED_AT,
                ),
            )


#: (state, license_type, field_key, value_num, value_bool, citation)
REQUIREMENTS_V1 = (
    ("TX", "MD", "renewal_cycle_months", Decimal(24), None, "Tex. Occ. Code 156.001"),
    ("TX", "MD", "renewal_window_days", Decimal(90), None, "22 Tex. Admin. Code 166.2"),
    ("TX", "MD", "csr_required", None, False, "Tex. Health & Safety Code 481.061"),
    ("TX", "MD", "ce_hours_total", Decimal(48), None, "22 Tex. Admin. Code 166.2(a)"),
    ("TX", "MD", "ce_topic_opioid_hours", Decimal(2), None, "22 Tex. Admin. Code 166.2(b)"),
    ("CA", "APRN", "renewal_cycle_months", Decimal(24), None, "Cal. Bus. & Prof. Code 2815"),
    ("CA", "APRN", "renewal_window_days", Decimal(60), None, "16 CCR 1484"),
    ("CA", "APRN", "csr_required", None, False, "Cal. Health & Safety Code 11100"),
    ("CA", "APRN", "ce_hours_total", Decimal(30), None, "16 CCR 1451"),
)


def seed_requirements(conn) -> None:
    """Load version 1 of the two states' rules."""
    with conn.cursor() as cur:
        for state, license_type, field_key, num, flag, citation in REQUIREMENTS_V1:
            cur.execute(
                """
                insert into requirements (state, license_type, field_key, value_num,
                                          value_bool, citation, effective_date,
                                          verified_at, verified_by, version, is_current)
                values (%s, %s, %s, %s, %s, %s, %s, %s, 'seed', 1, true)
                on conflict (state, license_type, field_key, version) do nothing
                """,
                (
                    state,
                    license_type,
                    field_key,
                    num,
                    flag,
                    citation,
                    date(2024, 1, 1),
                    GENERATED_AT,
                ),
            )


def bump_requirement(conn, state: str, license_type: str, field_key: str, value: Decimal) -> int:
    """Supersede one requirement with version+1, per 0004's versioning contract.

    The prior row loses ``is_current`` and the new one gains it, which is what
    ``ux_requirements_current`` enforces and what PRD 8.1 condition 5 reads.

    Returns:
        The new version number.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select version, citation from requirements
            where state = %s and license_type = %s and field_key = %s
              and is_current and deleted_at is null
            """,
            (state, license_type, field_key),
        )
        row = cur.fetchone()
        assert row is not None, f"no current {field_key} for {state}/{license_type}"
        version, citation = int(row[0]), row[1]
        cur.execute(
            """
            update requirements set is_current = false
            where state = %s and license_type = %s and field_key = %s and is_current
            """,
            (state, license_type, field_key),
        )
        cur.execute(
            """
            insert into requirements (state, license_type, field_key, value_num,
                                      citation, effective_date, verified_at,
                                      verified_by, version, is_current)
            values (%s, %s, %s, %s, %s, %s, %s, 'bump', %s, true)
            """,
            (
                state,
                license_type,
                field_key,
                value,
                citation,
                AS_OF,
                GENERATED_AT,
                version + 1,
            ),
        )
    return version + 1


# ===========================================================================
# Fixtures
# ===========================================================================
@pytest.fixture
def db_conn():
    """A migrated, empty database, rolled back to empty afterwards."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to a Postgres with db/migrations applied")
    psycopg = pytest.importorskip("psycopg")

    conn = psycopg.connect(url)
    with conn.cursor() as cur:
        cur.execute("select to_regclass('obligations')")
        row = cur.fetchone()
        if row is None or row[0] is None:
            for path in sorted(MIGRATIONS.glob("*.sql")):
                cur.execute(path.read_text())
    conn.commit()
    _truncate(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        _truncate(conn)
        conn.commit()
        conn.close()


def _truncate(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "truncate exceptions, obligations, ce_records, privileges, sanctions, "
            "enrollments, registrations, licenses, requirement_conflicts, "
            "requirements, affiliations, clinicians, practices, evidence "
            "restart identity cascade"
        )
    conn.commit()


@pytest.fixture
def seeded(db_conn):
    """The 20-clinician, two-state roster with version 1 of the rules."""
    seed_roster(db_conn)
    seed_requirements(db_conn)
    db_conn.commit()
    return db_conn


def fetch_obligations(conn, **where):
    """Return open obligations as dicts, newest engine state first."""
    clauses = ["deleted_at is null"]
    params: list = []
    for column, value in where.items():
        clauses.append(f"{column} = %s")
        params.append(value)
    with conn.cursor() as cur:
        cur.execute(
            "select id, clinician_id, practice_id, obligation_type, state, payer, "
            "due_date, window_opens, severity, status, rule_version, generated_at "
            "from obligations where " + " and ".join(clauses) + " order by due_date, id",
            params,
        )
        columns = [
            "id",
            "clinician_id",
            "practice_id",
            "obligation_type",
            "state",
            "payer",
            "due_date",
            "window_opens",
            "severity",
            "status",
            "rule_version",
            "generated_at",
        ]
        return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]


# ===========================================================================
# Pure unit tests -- no database
# ===========================================================================
@needs_engine
def test_add_months_clamps_to_end_of_month():
    """31 January plus one month is 28 February, not an error and not 3 March."""
    assert eng.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert eng.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert eng.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert eng.add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert eng.month_end(date(2026, 2, 3)) == date(2026, 2, 28)


@needs_engine
def test_compute_due_date_from_an_existing_credential_row():
    """With an expiry date, the duty is due then and opens a window before it."""
    rules = eng.RuleSet("TX", "MD", {})
    due, window = eng.compute_due_date(rules, "license_renewal", date(2027, 4, 30), AS_OF)
    assert due == date(2027, 4, 30)
    assert window == date(2027, 4, 30) - timedelta(days=90)


@needs_engine
def test_compute_due_date_without_a_credential_row_is_the_act_of_establishing_one():
    """No credential row means the obligation is to create one, actionable now."""
    rules = eng.RuleSet("TX", "MD", {})
    due, window = eng.compute_due_date(rules, "csr_renewal", None, AS_OF)
    assert due == AS_OF + timedelta(days=eng.DEFAULTS["establish_lead_days"])
    assert window == AS_OF


@needs_engine
def test_compute_due_date_leaves_a_past_due_date_in_the_past():
    """A lapse is a finding. Rolling it forward would hide it from severity."""
    rules = eng.RuleSet("TX", "MD", {})
    due, _ = eng.compute_due_date(rules, "license_renewal", AS_OF - timedelta(days=40), AS_OF)
    assert due < AS_OF


@needs_engine
def test_rule_version_is_the_highest_contributing_version():
    """A duty's rule_version traces to the newest rule that shaped it."""
    rules = eng.RuleSet(
        "TX",
        "MD",
        {
            "renewal_cycle_months": eng.Rule(
                "TX", "MD", "renewal_cycle_months", Decimal(24), None, None, 1
            ),
            "renewal_window_days": eng.Rule(
                "TX", "MD", "renewal_window_days", Decimal(90), None, None, 3
            ),
        },
    )
    assert rules.version_for("license_renewal") == 3
    assert rules.version_for("ce_cycle") is None


@needs_engine
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"exclusion_hit": True}, "critical"),
        ({"lapsed_license": True, "is_billing": True}, "critical"),
        ({"lapsed_license": True, "is_billing": False}, "elevated"),
        ({"enrollment_status": "terminated"}, "critical"),
        ({"enrollment_status": "rejected"}, "elevated"),
    ],
)
def test_severity_assignment_follows_prd_section_7(kwargs, expected):
    """PRD 7's severity table, case by case."""
    params = {"is_billing": True, **kwargs}
    severity, _ = eng.severity_for("license_renewal", AS_OF - timedelta(days=5), AS_OF, **params)
    assert severity == expected


@needs_engine
def test_revalidation_past_due_is_critical_but_a_past_due_screen_is_not():
    """Only revalidation is called out as critical when past due (PRD 7)."""
    severity, reason = eng.severity_for(
        "medicare_revalidation", AS_OF - timedelta(days=1), AS_OF, is_billing=True
    )
    assert (severity, reason) == ("critical", "revalidation past due")
    severity, _ = eng.severity_for(
        "license_renewal", AS_OF + timedelta(days=200), AS_OF, is_billing=True
    )
    assert severity == "routine"


@needs_engine
def test_monthly_exclusion_screen_is_not_permanently_elevated():
    """See the INTERPRETATION note in severity_for.

    Read literally, "due inside 30 days" makes every monthly screen elevated,
    and only routine may auto-clear. That would put PRD 11's auto-clear target
    out of reach by construction, so proximity is judged against the cadence.
    """
    severity, _ = eng.severity_for(
        "exclusion_screen",
        AS_OF + timedelta(days=12),
        AS_OF,
        is_billing=True,
        cadence_months=1,
    )
    assert severity == "routine"
    severity, _ = eng.severity_for(
        "license_renewal", AS_OF + timedelta(days=12), AS_OF, is_billing=True
    )
    assert severity == "elevated"


@needs_engine
def test_priority_ordering_returns_the_expected_sequence():
    """PRD 7: severity, then days-to-due ascending, then billing, then tier.

    The specs below are deliberately shuffled so that each tie-break has to do
    real work: the two criticals differ only in due date, the three routines
    only in billing flag and then only in tier.
    """

    def spec(name, severity, days, billing, tier):
        return eng.ObligationSpec(
            clinician_id=clinician_id(0),
            practice_id=PRACTICE_TX,
            obligation_type=name,
            state="TX",
            payer=None,
            due_date=AS_OF + timedelta(days=days),
            window_opens=AS_OF,
            severity=severity,
            rule_version=1,
            is_billing=billing,
            tier=tier,
        )

    unordered = [
        spec("f", "routine", 200, True, "essential"),
        spec("c", "elevated", 10, True, "standard"),
        spec("e", "routine", 200, True, "complete"),
        spec("a", "critical", -5, True, "standard"),
        spec("g", "routine", 200, False, "complete"),
        spec("b", "critical", 3, True, "complete"),
        spec("d", "elevated", 29, True, "complete"),
    ]
    ordered = eng.sort_by_priority(unordered, AS_OF)
    assert [s.obligation_type for s in ordered] == ["a", "b", "c", "d", "e", "f", "g"]


@needs_engine
def test_plan_is_deduplicated_on_the_open_duty_key():
    """Two facilities, one reappointment duty: the earlier date wins.

    ``ux_obligations_open_duty`` has no facility column, so the planner has to
    collapse them before the upsert does -- a single INSERT cannot touch the
    same conflict key twice.
    """
    cid = clinician_id(0)
    roster = eng.Roster(
        as_of=AS_OF,
        affiliations=[eng.Affiliation(cid, PRACTICE_TX, True, "complete")],
        licenses=[eng.License(cid, "TX", "MD", "active", date(2027, 6, 30), date(2020, 1, 1))],
        privileges=[
            eng.Privilege(cid, "St Elsewhere", date(2027, 11, 1), date(2025, 11, 1)),
            eng.Privilege(cid, "County General", date(2027, 2, 1), date(2025, 2, 1)),
        ],
    )
    specs = eng.plan(roster)
    reappointments = [s for s in specs if s.obligation_type == "privilege_reappointment"]
    assert len(reappointments) == 1
    assert reappointments[0].due_date == date(2027, 2, 1)
    assert len({s.key for s in specs}) == len(specs)


# ===========================================================================
# Database tests
# ===========================================================================
@pytest.mark.database
@needs_engine
def test_twenty_clinicians_two_states_make_a_twelve_month_calendar(seeded):
    """PRD 14 Phase 4 acceptance, verbatim.

    "Two loaded states generate a correct 12-month calendar for a seeded
    20-clinician roster."
    """
    result = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()

    rows = fetch_obligations(seeded)
    assert len(rows) == result.inserted == len(result.planned)
    assert result.updated == 0

    # Every clinician is screened for exclusions every month (PRD 7).
    screens = [r for r in rows if r["obligation_type"] == "exclusion_screen"]
    assert len(screens) == CLINICIAN_COUNT
    assert {r["due_date"] for r in screens} == {eng.month_end(AS_OF)}
    assert {r["severity"] for r in screens} == {"routine"}

    # One licence renewal per clinician, in both states.
    renewals = [r for r in rows if r["obligation_type"] == "license_renewal"]
    assert len(renewals) == CLINICIAN_COUNT
    assert {str(r["state"]).strip() for r in renewals} == {"TX", "CA"}

    # The calendar: twelve future renewals, one in each of the next twelve
    # months. Index 0 is deliberately already expired and index 11 has no
    # expiry date, so they are not part of the twelve.
    future = [r for r in renewals if r["due_date"] > AS_OF]
    months = sorted({(r["due_date"].year, r["due_date"].month) for r in future})
    expected = sorted(
        {
            (eng.add_months(AS_OF, offset).year, eng.add_months(AS_OF, offset).month)
            for offset in range(1, 13)
        }
    )
    assert months == expected

    # Every duty is dated, ordered and traceable.
    for row in rows:
        assert row["due_date"] is not None
        assert row["window_opens"] is None or row["window_opens"] <= row["due_date"]
        assert row["status"] == "pending"
        assert row["severity"] in ("routine", "elevated", "critical")
    for row in renewals:
        assert row["rule_version"] == 1, "a licence renewal must cite the rule that made it"

    # And each clinician's medicare enrolment produces its own dated duties.
    assert len([r for r in rows if r["obligation_type"] == "medicare_revalidation"]) == (
        CLINICIAN_COUNT
    )
    assert len([r for r in rows if r["obligation_type"] == "directory_attestation"]) == (
        CLINICIAN_COUNT
    )


@pytest.mark.database
@needs_engine
def test_running_twice_produces_no_duplicates(seeded):
    """The ``ux_obligations_open_duty`` test.

    The nightly job runs every night against a roster that has not changed. If
    ``ON CONFLICT`` fails to infer the partial index the second run inserts a
    second copy of every duty, the action queue doubles overnight, and nothing
    raises. So: run twice, count, and compare identities row by row.
    """
    first = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()
    before = {r["id"]: r for r in fetch_obligations(seeded)}
    assert len(before) == first.inserted > 0

    second = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT + timedelta(days=1))
    seeded.commit()
    after = {r["id"]: r for r in fetch_obligations(seeded)}

    assert second.inserted == 0, "a second run must create nothing"
    assert second.updated == 0, "an unchanged roster must move nothing"
    assert second.unchanged == len(second.planned)
    assert set(after) == set(before), "the same rows, with the same ids"

    # generated_at only advances when something actually moved, so "what did
    # last night change" stays answerable from the table.
    for oid, row in after.items():
        assert row["generated_at"] == before[oid]["generated_at"]

    # And the invariant the index exists to protect, stated directly.
    with seeded.cursor() as cur:
        cur.execute(
            """
            select count(*) from (
                select clinician_id, practice_id, obligation_type,
                       coalesce(state, ''), coalesce(payer, '')
                from obligations
                where status in ('pending','queued','in_progress','exception')
                  and deleted_at is null
                group by 1, 2, 3, 4, 5
                having count(*) > 1
            ) duplicated
            """
        )
        assert cur.fetchone()[0] == 0


@pytest.mark.database
@needs_engine
def test_the_upsert_targets_the_open_duty_index_and_nothing_else(seeded):
    """The conflict target is the contract with 0005, so state it out loud.

    Two negative controls: dropping the index predicate, and naming the columns
    without their ``coalesce`` wrappers. Both must be rejected by the server.
    If a later migration reshapes ``ux_obligations_open_duty``, this test names
    the file to go and read.
    """
    with seeded.cursor() as cur:
        cur.execute("select indexdef from pg_indexes where indexname = 'ux_obligations_open_duty'")
        row = cur.fetchone()
    assert row is not None, "0005_obligations.sql must have been applied"
    indexdef = row[0].lower()
    for fragment in (
        "clinician_id",
        "practice_id",
        "obligation_type",
        "coalesce(state,",
        "coalesce(payer,",
    ):
        assert fragment in indexdef
        assert fragment in eng.UPSERT_SQL.lower()
    for status in eng.OPEN_STATUSES:
        assert f"'{status}'" in indexdef
        assert f"'{status}'" in eng.UPSERT_SQL
    assert "deleted_at is null" in indexdef and "deleted_at is null" in eng.UPSERT_SQL
    # due_date is the whole point of the design: it is NOT part of the key.
    assert "due_date" not in indexdef.split(" where ")[0]

    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()
    psycopg = pytest.importorskip("psycopg")

    broken = [
        # No index predicate: nothing to match a partial index.
        """
        insert into obligations (clinician_id, practice_id, obligation_type, state,
                                 payer, due_date, severity, status, generated_at)
        select clinician_id, practice_id, obligation_type, state, payer, due_date,
               severity, 'pending', now() from obligations limit 1
        on conflict (clinician_id, practice_id, obligation_type,
                     coalesce(state, ''), coalesce(payer, ''))
        do update set due_date = excluded.due_date
        """,
        # Bare columns: the index is over expressions, not columns.
        """
        insert into obligations (clinician_id, practice_id, obligation_type, state,
                                 payer, due_date, severity, status, generated_at)
        select clinician_id, practice_id, obligation_type, state, payer, due_date,
               severity, 'pending', now() from obligations limit 1
        on conflict (clinician_id, practice_id, obligation_type, state, payer)
        where status in ('pending','queued','in_progress','exception')
          and deleted_at is null
        do update set due_date = excluded.due_date
        """,
    ]
    for statement in broken:
        try:
            with seeded.transaction(), seeded.cursor() as cur:
                cur.execute(statement)
        except psycopg.Error as exc:
            assert "no unique or exclusion constraint" in str(exc)
        else:  # pragma: no cover - a passing variant would be the bug
            raise AssertionError("a near-miss conflict target was accepted")


@pytest.mark.database
@needs_engine
def test_a_requirements_version_bump_moves_the_due_date_in_place(seeded):
    """A new rule version moves the open duty; it does not fork a second one.

    Clinician ``NO_EXPIRY_INDEX`` holds a Texas licence with an issue date and
    no expiry, so its renewal is dated from ``renewal_cycle_months``. Bumping
    that rule from 24 to 36 months must move the same row's ``due_date`` and
    ``rule_version`` and leave its id alone -- an obligation that forks on a
    rule change is a duplicated queue item, and the queue is the product.
    """
    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()

    cid = clinician_id(NO_EXPIRY_INDEX)
    before = fetch_obligations(seeded, clinician_id=cid, obligation_type="license_renewal")
    assert len(before) == 1
    assert before[0]["due_date"] == eng.add_months(NO_EXPIRY_ISSUE, 24)
    assert before[0]["rule_version"] == 1

    new_version = bump_requirement(seeded, "TX", "MD", "renewal_cycle_months", Decimal(36))
    seeded.commit()
    assert new_version == 2

    result = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT + timedelta(days=1))
    seeded.commit()

    after = fetch_obligations(seeded, clinician_id=cid, obligation_type="license_renewal")
    assert len(after) == 1, "a rule change must not fork a second obligation"
    assert after[0]["id"] == before[0]["id"], "in place: the same row"
    assert after[0]["due_date"] == eng.add_months(NO_EXPIRY_ISSUE, 36)
    assert after[0]["rule_version"] == 2
    assert after[0]["generated_at"] > before[0]["generated_at"]
    assert result.inserted == 0
    assert result.updated >= 1


@pytest.mark.database
@needs_engine
def test_expired_licence_is_critical_only_while_billing(seeded):
    """PRD 7: "license expired or suspended while ``is_billing`` is true".

    Same clinician, same expired licence, one flag flipped. The severity has to
    follow the flag, and it has to follow it on the existing row.
    """
    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()

    cid = clinician_id(EXPIRED_INDEX)
    billing = fetch_obligations(seeded, clinician_id=cid, obligation_type="license_renewal")
    assert len(billing) == 1
    assert billing[0]["severity"] == "critical"
    assert billing[0]["due_date"] < AS_OF

    with seeded.cursor() as cur:
        cur.execute("update affiliations set is_billing = false where clinician_id = %s", (cid,))
    seeded.commit()

    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT + timedelta(days=1))
    seeded.commit()

    non_billing = fetch_obligations(seeded, clinician_id=cid, obligation_type="license_renewal")
    assert len(non_billing) == 1
    assert non_billing[0]["id"] == billing[0]["id"]
    assert non_billing[0]["severity"] != "critical"
    # Still overdue, so still worth a person's attention -- just not the
    # same-day, account-lead-notified kind.
    assert non_billing[0]["severity"] == "elevated"


@pytest.mark.database
@needs_engine
def test_the_queue_comes_back_in_priority_order(seeded):
    """PRD 7 ordering, end to end, against rows the engine actually wrote."""
    result = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()

    keys = [eng.priority_key(spec, AS_OF) for spec in result.planned]
    assert keys == sorted(keys), "run() returns the plan in queue order"

    severities = [spec.severity for spec in result.planned]
    assert severities[0] == "critical"
    assert eng.SEVERITY_RANK[severities[0]] <= eng.SEVERITY_RANK[severities[-1]]

    # The critical expired licence is the first thing a human sees.
    assert result.planned[0].clinician_id == clinician_id(EXPIRED_INDEX)
    assert result.planned[0].obligation_type == "license_renewal"

    # And the same ordering expressed in SQL agrees with the Python one.
    with seeded.cursor() as cur:
        cur.execute(
            """
            select o.severity, o.due_date, a.is_billing, p.tier
            from obligations o
            join affiliations a
              on a.clinician_id = o.clinician_id and a.practice_id = o.practice_id
            join practices p on p.id = o.practice_id
            where o.deleted_at is null
            """
            + eng.PRIORITY_ORDER_SQL
        )
        ordered = cur.fetchall()
    ranks = [
        (
            eng.SEVERITY_RANK[row[0]],
            (row[1] - date.today()).days,
            0 if row[2] else 1,
            eng.TIER_RANK[row[3]],
        )
        for row in ordered
    ]
    assert ranks == sorted(ranks)


@pytest.mark.database
@needs_engine
def test_dry_run_writes_nothing_but_reports_what_it_would_do(seeded):
    """``engine run --dry-run``: the plan, the counts, and an untouched table."""
    dry = eng.run(seeded, as_of=AS_OF, dry_run=True, generated_at=GENERATED_AT)
    seeded.commit()
    assert fetch_obligations(seeded) == []
    assert dry.dry_run is True
    assert dry.inserted == len(dry.planned) > 0
    assert dry.updated == 0 and dry.unchanged == 0

    live = eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()
    assert live.inserted == dry.inserted

    again = eng.run(seeded, as_of=AS_OF, dry_run=True, generated_at=GENERATED_AT)
    assert again.inserted == 0
    assert again.unchanged == len(again.planned)
    assert len(fetch_obligations(seeded)) == live.inserted


@pytest.mark.database
@needs_engine
def test_a_completed_obligation_lets_the_next_cycle_insert_cleanly(seeded):
    """Terminal rows drop out of the index predicate, by design (0005).

    Next month's exclusion screen must be a new row, not an edit of the one the
    team already closed, or the audit trail loses a month.
    """
    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()
    cid = clinician_id(0)
    screens = fetch_obligations(seeded, clinician_id=cid, obligation_type="exclusion_screen")
    assert len(screens) == 1

    with seeded.cursor() as cur:
        cur.execute(
            "update obligations set status = 'complete', completed_at = now() where id = %s",
            (screens[0]["id"],),
        )
    seeded.commit()

    next_month = eng.add_months(AS_OF, 1)
    eng.run(seeded, as_of=next_month, generated_at=GENERATED_AT + timedelta(days=31))
    seeded.commit()

    all_screens = fetch_obligations(seeded, clinician_id=cid, obligation_type="exclusion_screen")
    assert len(all_screens) == 2
    assert {r["status"] for r in all_screens} == {"complete", "pending"}
    fresh = next(r for r in all_screens if r["status"] == "pending")
    assert fresh["due_date"] == eng.month_end(next_month)


@pytest.mark.database
@needs_engine
def test_an_exclusion_hit_makes_the_screen_critical(seeded):
    """PRD 7's first critical condition, and PRD 8.3's HIGH_CONSEQUENCE."""
    cid = clinician_id(4)
    with seeded.cursor() as cur:
        cur.execute(
            """
            insert into sanctions (clinician_id, source, action_type, action_date,
                                   match_confidence, evidence_id)
            values (%s, 'leie', '1128(a)(1)', %s, 1.00, %s)
            """,
            (cid, date(2026, 5, 1), EVIDENCE_ID),
        )
    seeded.commit()

    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()

    screen = fetch_obligations(seeded, clinician_id=cid, obligation_type="exclusion_screen")
    assert len(screen) == 1
    assert screen[0]["severity"] == "critical"
    clean = fetch_obligations(
        seeded, clinician_id=clinician_id(5), obligation_type="exclusion_screen"
    )
    assert clean[0]["severity"] == "routine"


@pytest.mark.database
@needs_engine
def test_an_ended_affiliation_generates_nothing(seeded):
    """PRD 7 loops over ACTIVE affiliations: end_date null or in the future."""
    cid = clinician_id(7)
    with seeded.cursor() as cur:
        cur.execute(
            "update affiliations set end_date = %s where clinician_id = %s",
            (AS_OF - timedelta(days=1), cid),
        )
    seeded.commit()

    eng.run(seeded, as_of=AS_OF, generated_at=GENERATED_AT)
    seeded.commit()
    assert fetch_obligations(seeded, clinician_id=cid) == []
    assert fetch_obligations(seeded, clinician_id=clinician_id(8)) != []
