"""CRM dedupe and suppression (BUILD_PLAN WP1.4).

Database-marked, because the dedupe rules the plan asks for are enforced by the
schema (0016): same PAC ID one org, same email one contact, suppression across
brands. The one pure test is the guard that an organization must carry a key.
"""

from __future__ import annotations

import pytest

from clinician_standing import crm


def _add_practice(cur, pac: str, name: str = "Test Practice") -> None:
    cur.execute(
        "insert into practices (org_pac_id, legal_name) values (%s, %s)",
        (pac, name),
    )


def test_upsert_organization_requires_a_key() -> None:
    with pytest.raises(ValueError, match="org_pac_id or an internal_ref"):
        crm.upsert_organization(None, legal_name="No Key Co")  # type: ignore[arg-type]


@pytest.mark.database
def test_sync_from_practices_is_idempotent(db_connection) -> None:
    with db_connection.cursor() as cur:
        _add_practice(cur, "PAC0000001")
        _add_practice(cur, "PAC0000002")
    first = crm.sync_organizations_from_practices(db_connection)
    second = crm.sync_organizations_from_practices(db_connection)
    assert first == 2
    assert second == 0  # rerun creates no duplicates
    with db_connection.cursor() as cur:
        cur.execute("select count(*) from organizations")
        assert cur.fetchone()[0] == 2


@pytest.mark.database
def test_upsert_organization_dedupes_on_pac(db_connection) -> None:
    a = crm.upsert_organization(db_connection, legal_name="Acme", org_pac_id="PAC9")
    b = crm.upsert_organization(db_connection, legal_name="Acme (again)", org_pac_id="PAC9")
    assert a == b


@pytest.mark.database
def test_upsert_contact_dedupes_on_email_case_insensitively(db_connection) -> None:
    org = crm.upsert_organization(db_connection, legal_name="Acme", internal_ref="acme")
    a = crm.upsert_contact(db_connection, organization_id=org, email="Jane@Acme.COM")
    b = crm.upsert_contact(db_connection, organization_id=org, email="jane@acme.com")
    assert a == b


@pytest.mark.database
def test_all_scope_suppression_applies_to_every_brand(db_connection) -> None:
    crm.suppress(db_connection, reason="unsubscribe", email="stop@x.com")
    assert crm.is_suppressed(db_connection, "stop@x.com") is True
    assert crm.is_suppressed(db_connection, "stop@x.com", brand="cliniciq") is True
    assert crm.is_suppressed(db_connection, "other@x.com") is False


@pytest.mark.database
def test_domain_suppression_covers_every_address_at_the_domain(db_connection) -> None:
    crm.suppress(db_connection, reason="complaint", domain="blocked.com")
    assert crm.is_suppressed(db_connection, "anyone@blocked.com") is True
    assert crm.is_suppressed(db_connection, "anyone@allowed.com") is False


@pytest.mark.database
def test_brand_scoped_suppression_is_only_that_brand(db_connection) -> None:
    crm.suppress(db_connection, reason="manual", email="ciq@x.com", brand_scope="cliniciq")
    assert crm.is_suppressed(db_connection, "ciq@x.com", brand="cliniciq") is True
    assert crm.is_suppressed(db_connection, "ciq@x.com", brand="whitecoat") is False
    # No brand given: only all-scope entries apply, so this is not suppressed.
    assert crm.is_suppressed(db_connection, "ciq@x.com") is False
