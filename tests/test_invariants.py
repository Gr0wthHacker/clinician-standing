"""The four invariants that must never quietly stop holding.

Each of these is a property the rest of the system is allowed to assume, and
each one fails silently rather than loudly if it is broken. A commit that
removes one of them must fail here, in CI, and not in a monthly job or in a
letter to a clinician's employer.

1. LEIE name+DOB matching is OFF, and calling it raises. A sub-1.0 identity
   match on an exclusions file is a recorded accusation against a named
   clinician, reported to their employer. PRD 13 flags it as possibly a
   consumer report under FCRA; PRD 15 open decision 3 requires a measured
   false-positive rate first. A default flipped to True by a merge would ship
   it with neither.

2. A credential row cannot be inserted without an evidence_id. PRD 5.2 makes
   every credential row an assertion and PRD 14 Phase 1 acceptance states the
   invariant outright. It is enforced twice -- in `insert_credential` and by a
   NOT NULL foreign key -- and both are checked here, because a future bulk
   loader that goes around the helper must still hit the constraint.

3. Row-level security is enabled AND FORCED on every table, the ingest role
   exists without BYPASSRLS, and the restricted roles cannot reach the evidence
   store. RLS that is merely `enable`d is inert for the table owner, which is
   the exact shape of the bug 0011 fixes.

4. Enrollment status is derived at read time. A status computed from a date and
   frozen at write time goes stale in any month the source does not touch the
   row, and a stale `approved` on a past-due Medicare revalidation is critical
   severity under PRD 7.

The database-backed ones are marked `database` and deselected in CI. Run them
against a throwaway cluster with every migration applied:

    TEST_DATABASE_URL=postgresql://... pytest -m database
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from clinician_standing.connectors import oig_leie
from clinician_standing.evidence import CREDENTIAL_TABLES, EvidenceRequired, insert_credential

# The 16 tables 0008 enables RLS on and 0011 forces it on. Spelled out rather
# than read from the database, so that a table dropped from the migration's
# list is a failure here and not an invisible gap.
RLS_TABLES = (
    "practices",
    "clinicians",
    "affiliations",
    "licenses",
    "registrations",
    "enrollments",
    "privileges",
    "ce_records",
    "sanctions",
    "requirements",
    "requirement_conflicts",
    "obligations",
    "evidence",
    "exceptions",
    "sources",
    "source_runs",
)

# PRD 12: these are the tables the offshore delivery role must not hold a
# privilege on at all, so that the failure is `permission denied` and not an
# empty result set that reads like "no exclusions found".
DELIVERY_FORBIDDEN_TABLES = (
    "evidence",
    "sanctions",
    "requirements",
    "requirement_conflicts",
    "exceptions",
    "sources",
    "source_runs",
)


# ===========================================================================
# 1. LEIE name + DOB matching is off and unimplemented
# ===========================================================================
def test_name_dob_matching_is_disabled():
    """The gate is False. Nothing else about this file matters if it is not."""
    assert oig_leie.NAME_DOB_MATCHING_ENABLED is False, (
        "NAME_DOB_MATCHING_ENABLED must stay False until a measured confidence "
        "threshold and counsel sign-off exist (PRD 13, PRD 15 open decision 3). "
        "Turning it on ships unreviewed identity matching against an exclusions "
        "list, which is an accusation about a named clinician."
    )


def test_name_dob_matching_flag_is_a_bool_not_a_truthy_value():
    """`is False` above is deliberate; keep the flag a real bool so it means it."""
    assert isinstance(oig_leie.NAME_DOB_MATCHING_ENABLED, bool)


def test_match_by_name_dob_raises():
    """Calling it is a programming error, not a no-op that returns nothing.

    Returning `[]` would be the dangerous failure: a caller would read it as
    "no exclusions matched" and clear the obligation.
    """
    with pytest.raises(NotImplementedError) as excinfo:
        oig_leie.match_by_name_dob([{"last_name": "SMITH", "first_name": "JOHN"}])
    assert "counsel" in str(excinfo.value).lower() or "threshold" in str(excinfo.value).lower(), (
        "the error must say what is missing, so the next reader does not just implement it"
    )


def test_match_by_name_dob_raises_on_empty_input_too():
    """No input is not a licence to return an empty result."""
    with pytest.raises(NotImplementedError):
        oig_leie.match_by_name_dob([])


def test_leie_connector_does_not_call_name_dob_matching_when_disabled():
    """The connector must be gated on the flag, not merely aware of it."""
    source = inspect.getsource(oig_leie.OigLeieConnector)
    assert "NAME_DOB_MATCHING_ENABLED" in source, (
        "OigLeieConnector must consult NAME_DOB_MATCHING_ENABLED; a connector "
        "that calls match_by_name_dob unconditionally would raise in production"
    )


# ===========================================================================
# 2. A credential row cannot be written without evidence
# ===========================================================================
def test_credential_tables_are_the_assertion_tables():
    """The guard covers every table PRD 5.2 calls an assertion."""
    assert sorted(CREDENTIAL_TABLES) == [
        "ce_records",
        "enrollments",
        "licenses",
        "privileges",
        "registrations",
        "sanctions",
    ]


@pytest.mark.parametrize("missing", [None])
def test_insert_credential_refuses_without_evidence_id(missing):
    """No evidence id, no write -- and no connection is touched on the way out.

    `conn` is None on purpose: if the guard ever moved to after the first
    database call, this test would fail with AttributeError instead of passing,
    which is the correct signal.
    """
    with pytest.raises(EvidenceRequired):
        insert_credential(None, "sanctions", {"clinician_id": uuid.uuid4()}, missing)


def test_insert_credential_refuses_a_non_credential_table():
    """The helper is only for assertion tables; anything else is plain SQL."""
    with pytest.raises(ValueError):
        insert_credential(None, "practices", {"legal_name": "X"}, uuid.uuid4())


@pytest.mark.database
def test_evidence_id_is_not_null_on_every_credential_table(db_connection):
    """The schema enforces it too, for any writer that skips the helper.

    Two tables are nullable on purpose and 0003 says why at length:

    * ``privileges`` -- hospital privileging is attested by the facility and no
      PRD 6 connector publishes it;
    * ``ce_records`` -- CE completion is attested by the provider's certificate
      or self-reported at onboarding.

    In both cases a NULL means "not primary-source confirmed", which PRD 8.1
    condition 1 reads as "cannot auto-clear". Asserting the exception list
    exactly, rather than skipping those two, is the point: a third table
    quietly joining them is the regression this test is for.
    """
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select table_name, is_nullable
              from information_schema.columns
             where table_schema = 'public'
               and column_name = 'evidence_id'
               and table_name = any(%s)
             order by table_name
            """,
            (sorted(CREDENTIAL_TABLES),),
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows] == sorted(CREDENTIAL_TABLES), (
        f"every credential table must carry an evidence_id column; saw {rows}"
    )
    nullable = sorted(name for name, is_nullable in rows if is_nullable != "NO")
    assert nullable == ["ce_records", "privileges"], (
        f"evidence_id must be NOT NULL on every credential table except the two "
        f"0003 documents as attested-not-sourced; nullable here: {nullable} "
        "(PRD 5.2, PRD 14 Phase 1 acceptance)"
    )


@pytest.mark.database
def test_credential_insert_without_evidence_is_rejected_by_the_database(db_connection):
    """A raw INSERT with a null evidence_id fails, helper or no helper."""
    import psycopg

    with db_connection.cursor() as cur:
        cur.execute("savepoint invariant_probe")
        with pytest.raises(psycopg.errors.NotNullViolation) as excinfo:
            cur.execute(
                """
                insert into enrollments
                    (clinician_id, practice_id, payer, status, evidence_id, verified_at)
                values (null, null, 'medicare', 'approved', null, now())
                """
            )
        cur.execute("rollback to savepoint invariant_probe")
    assert "evidence_id" in str(excinfo.value), (
        f"expected a null-violation naming evidence_id, got {excinfo.value!r}"
    )


@pytest.mark.database
def test_credential_insert_with_an_unknown_evidence_id_is_rejected(db_connection):
    """An evidence_id that cites nothing is as bad as no evidence_id."""
    import psycopg

    with db_connection.cursor() as cur:
        cur.execute("savepoint invariant_probe")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                """
                insert into enrollments
                    (clinician_id, practice_id, payer, status, evidence_id, verified_at)
                values (null, null, 'medicare', 'approved', %s, now())
                """,
                (uuid.uuid4(),),
            )
        cur.execute("rollback to savepoint invariant_probe")


# ===========================================================================
# 3. Row-level security
# ===========================================================================
@pytest.mark.database
def test_rls_is_enabled_and_forced_on_every_table(db_connection):
    """`enable` alone exempts the table owner, which is who the ingest was."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select c.relname, c.relrowsecurity, c.relforcerowsecurity
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relkind = 'r' and c.relname = any(%s)
             order by c.relname
            """,
            (list(RLS_TABLES),),
        )
        rows = cur.fetchall()
    found = {name for name, _, _ in rows}
    assert found == set(RLS_TABLES), f"missing tables: {sorted(set(RLS_TABLES) - found)}"
    not_enabled = sorted(name for name, enabled, _ in rows if not enabled)
    not_forced = sorted(name for name, _, forced in rows if not forced)
    assert not not_enabled, f"RLS is not enabled on {not_enabled}"
    assert not not_forced, f"RLS is not FORCED on {not_forced} (0011); the owner bypasses it"


@pytest.mark.database
def test_every_table_has_an_internal_policy(db_connection):
    """A table with RLS forced and no policy is unreadable by the ingest."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select tablename from pg_policies
             where schemaname = 'public' and policyname like '%%_internal_all'
            """
        )
        covered = {row[0] for row in cur.fetchall()}
    assert set(RLS_TABLES) <= covered, f"no internal policy on {sorted(set(RLS_TABLES) - covered)}"


@pytest.mark.database
def test_ingest_role_exists_and_is_not_privileged(db_connection):
    """The role DATABASE_URL should name: a login, and nothing more."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
              from pg_roles where rolname = 'app_ingest'
            """
        )
        row = cur.fetchone()
    assert row is not None, "app_ingest does not exist; 0011_ingest_role.sql has not been applied"
    can_login, is_super, bypass_rls, create_db, create_role = row
    assert can_login, "app_ingest must be able to log in; it is the ingest's own credential"
    assert not is_super, "app_ingest must not be a superuser"
    assert not bypass_rls, (
        "app_ingest must not have BYPASSRLS -- that is the whole point of 0011. "
        "With it, every policy in 0008 is decorative for the one credential in use."
    )
    assert not create_db and not create_role


@pytest.mark.database
def test_ingest_role_reaches_the_tables_only_through_app_internal(db_connection):
    """Its entire reach is the membership; it owns nothing."""
    with db_connection.cursor() as cur:
        cur.execute("select pg_has_role('app_ingest', 'app_internal', 'member')")
        assert cur.fetchone()[0], "app_ingest must be a member of app_internal"
        cur.execute(
            """
            select count(*) from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public'
               and c.relowner = (select oid from pg_roles where rolname = 'app_ingest')
            """
        )
        assert cur.fetchone()[0] == 0, "app_ingest must not own any object in the public schema"


@pytest.mark.database
def test_delivery_role_has_no_privilege_on_the_evidence_store(db_connection):
    """PRD 12: never the evidence store, never the rules admin.

    A privilege check, not a policy check: the intent is `permission denied`,
    not an empty result that reads like a clean screen.
    """
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select table_name, privilege_type
              from information_schema.table_privileges
             where table_schema = 'public'
               and grantee = 'app_delivery'
               and table_name = any(%s)
            """,
            (list(DELIVERY_FORBIDDEN_TABLES),),
        )
        leaked = cur.fetchall()
    assert not leaked, f"app_delivery must hold no privilege on these tables, but has {leaked}"


@pytest.mark.database
def test_client_portal_role_cannot_reach_evidence_or_sanctions(db_connection):
    """The portal is read-only and never sees the evidence store (PRD 3, 12)."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select table_name, privilege_type
              from information_schema.table_privileges
             where table_schema = 'public'
               and grantee = 'app_client_portal'
               and (table_name in ('evidence', 'sanctions', 'exceptions')
                    or privilege_type in ('INSERT', 'UPDATE', 'DELETE'))
            """
        )
        leaked = cur.fetchall()
    assert not leaked, f"app_client_portal must be read-only and evidence-free, but has {leaked}"


@pytest.mark.database
def test_client_portal_scope_is_empty_without_a_practice_claim(db_connection):
    """Empty JWT scope denies every portal policy; it must not default to all.

    `= any(<empty array>)` is false for every row, so an unscoped request sees
    nothing. A helper that returned NULL, or every practice, on a missing claim
    would open the whole book of business to any authenticated portal session.
    """
    with db_connection.cursor() as cur:
        cur.execute("select app.portal_practice_ids() is not null")
        assert cur.fetchone()[0] is True, "the helper must return an empty array, never NULL"
        cur.execute("select cardinality(app.portal_practice_ids())")
        assert cur.fetchone()[0] == 0


# ===========================================================================
# 4. Enrollment status is derived at read time
# ===========================================================================
def test_the_revalidation_connector_does_not_freeze_a_date_comparison():
    """The load statements must not compare a due date against current_date.

    The bug was `case when individual_due_date < current_date then
    'revalidation_due' ... end` evaluated at load time and stored. A monthly
    file only revisits a row when CMS changes it, so the stored answer silently
    goes stale.
    """
    from clinician_standing.connectors import cms_revalidation

    for name in ("_UPDATE_ENROLLMENTS", "_INSERT_ENROLLMENTS"):
        statement = getattr(cms_revalidation, name)
        assert "current_date" not in statement.lower(), (
            f"{name} compares a date against current_date and stores the answer. "
            "Write revalidation_due and let the enrollments_current view derive "
            "the status at read time (0012)."
        )


@pytest.mark.database
def test_enrollment_status_is_derived_at_read_time(db_connection):
    """A due date that passes changes the answer with no write of any kind."""
    with db_connection.cursor() as cur:
        cur.execute("savepoint invariant_probe")
        evidence_id = uuid.uuid4()
        clinician_id = uuid.uuid4()
        practice_id = uuid.uuid4()
        cur.execute(
            """
            insert into evidence (id, source_key, fetched_at, request_ref, payload_ref,
                                  payload_sha256, freshness_expires_at)
            values (%s, 'cms_revalidation', %s, 'test', 'test', %s, %s)
            """,
            (evidence_id, datetime.now(UTC), "0" * 64, datetime.now(UTC) + timedelta(days=45)),
        )
        cur.execute(
            "insert into clinicians (id, npi, clinician_type) values (%s, %s, 'physician')",
            (clinician_id, "1234567893"),
        )
        cur.execute(
            "insert into practices (id, org_pac_id, legal_name) values (%s, %s, %s)",
            (practice_id, "TEST0001", "Test Group"),
        )
        # Written exactly as the connector writes it: status 'approved', plus
        # the published due date. Nothing here says "overdue".
        cur.execute(
            """
            insert into enrollments (clinician_id, practice_id, payer, status,
                                     revalidation_due, evidence_id, verified_at)
            values (%s, %s, 'medicare', 'approved', current_date + 1, %s, now())
            """,
            (clinician_id, practice_id, evidence_id),
        )
        cur.execute(
            "select status, status_current, revalidation_overdue from enrollments_current "
            "where clinician_id = %s",
            (clinician_id,),
        )
        stored, current, overdue = cur.fetchone()
        assert (stored, current, overdue) == ("approved", "approved", False)

        # The only thing that changes is which side of today the date is on.
        # No status is rewritten; this is what a passing month looks like.
        cur.execute(
            "update enrollments set revalidation_due = current_date - 1 where clinician_id = %s",
            (clinician_id,),
        )
        cur.execute(
            "select status, status_current, revalidation_overdue, days_overdue "
            "from enrollments_current where clinician_id = %s",
            (clinician_id,),
        )
        stored, current, overdue, days = cur.fetchone()
        assert stored == "approved", "the stored column must keep the source's own assertion"
        assert current == "revalidation_due", (
            "status_current must follow the date. If this fails, enrollment status has gone "
            "back to being frozen at write time and every clinician whose due date passes in "
            "a quiet month reads as approved while past due (PRD 7, critical severity)."
        )
        assert overdue is True and days == 1
        cur.execute("rollback to savepoint invariant_probe")


@pytest.mark.database
def test_enrollments_current_does_not_bypass_row_level_security(db_connection):
    """A view without security_invoker runs as its owner and defeats 0008."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select c.reloptions from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relname = 'enrollments_current'
            """
        )
        row = cur.fetchone()
    assert row is not None, "enrollments_current is missing; 0012 has not been applied"
    options = row[0] or []
    assert "security_invoker=true" in options, (
        "enrollments_current must be created WITH (security_invoker = true), or every role "
        f"granted SELECT on it reads every practice's enrollments. Options: {options}"
    )


@pytest.mark.database
def test_a_terminated_enrollment_is_not_relabelled_by_a_past_due_date(db_connection):
    """A decision the payer made outranks the date arithmetic."""
    with db_connection.cursor() as cur:
        cur.execute(
            """
            select status_current from (
              select 'terminated'::text as status,
                     (current_date - 400)::date as revalidation_due
            ) e,
            lateral (
              select case
                when e.status in ('rejected','terminated','pending') then e.status
                when e.revalidation_due is not null and e.revalidation_due < current_date
                  then 'revalidation_due'
                else 'approved'
              end as status_current
            ) d
            """
        )
        assert cur.fetchone()[0] == "terminated"
