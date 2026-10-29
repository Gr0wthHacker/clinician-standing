"""CRM helpers: idempotent org/contact upserts and suppression (WP1.4).

The dedupe rules are the database's (0016): same PAC ID is the same
organization, same email is the same contact, and a fuzzy match is never
auto-merged. These helpers write through those constraints so that loading the
same prospects twice creates no duplicates, and reading suppression honors it
across every brand.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

__all__ = [
    "is_suppressed",
    "suppress",
    "sync_organizations_from_practices",
    "upsert_contact",
    "upsert_organization",
]


def sync_organizations_from_practices(conn: psycopg.Connection) -> int:
    """Create a CRM organization for every practice, idempotent on PAC ID.

    Links the CRM plane to the DAC roster: each practice with an ``org_pac_id``
    gets one ``organizations`` row. ``on conflict do nothing`` makes a re-run a
    no-op, so loading the same prospects twice adds no duplicates.

    Returns:
        The number of organizations inserted this call.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into organizations (org_pac_id, legal_name, dba_name, segment)
            select p.org_pac_id, p.legal_name, p.dba_name, 'practice'
            from practices p
            where p.org_pac_id is not null and p.deleted_at is null
            on conflict (org_pac_id) do nothing
            """
        )
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def upsert_organization(
    conn: psycopg.Connection,
    *,
    legal_name: str,
    org_pac_id: str | None = None,
    internal_ref: str | None = None,
    segment: str | None = None,
) -> UUID:
    """Insert or return an organization, deduped on PAC ID then internal ref.

    Raises:
        ValueError: If neither ``org_pac_id`` nor ``internal_ref`` is given --
            an organization needs a stable key to dedupe on.
    """
    if not org_pac_id and not internal_ref:
        raise ValueError("upsert_organization needs an org_pac_id or an internal_ref")
    with conn.cursor() as cur:
        if org_pac_id:
            cur.execute("select id from organizations where org_pac_id = %s", (org_pac_id,))
        else:
            cur.execute(
                "select id from organizations where internal_ref = %s and deleted_at is null",
                (internal_ref,),
            )
        existing = cur.fetchone()
        if existing is not None:
            return cast(UUID, existing[0])
        cur.execute(
            """
            insert into organizations (org_pac_id, internal_ref, legal_name, segment)
            values (%s, %s, %s, %s)
            returning id
            """,
            (org_pac_id, internal_ref, legal_name, segment),
        )
        row = cur.fetchone()
        assert row is not None
        return cast(UUID, row[0])


def upsert_contact(
    conn: psycopg.Connection,
    *,
    organization_id: UUID,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    source: str | None = None,
    confidence: float | None = None,
) -> UUID:
    """Insert or return a contact, deduped case-insensitively on email."""
    with conn.cursor() as cur:
        cur.execute("select id from contacts where lower(email) = lower(%s)", (email,))
        existing = cur.fetchone()
        if existing is not None:
            return cast(UUID, existing[0])
        cur.execute(
            """
            insert into contacts (organization_id, email, first_name, last_name, source, confidence)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (organization_id, email, first_name, last_name, source, confidence),
        )
        row = cur.fetchone()
        assert row is not None
        return cast(UUID, row[0])


def _domain_of(email: str) -> str | None:
    """Return the lowercased domain of an email, or None."""
    return email.rsplit("@", 1)[-1].lower() if "@" in email else None


def is_suppressed(conn: psycopg.Connection, email: str, *, brand: str | None = None) -> bool:
    """True when ``email`` (or its domain) is on the suppression list.

    An ``all`` scope suppresses for every brand; a brand-scoped entry suppresses
    only that brand. With no ``brand`` given, only ``all``-scope entries apply.
    """
    if not email:
        return False
    scopes = ["all"] + ([brand] if brand else [])
    with conn.cursor() as cur:
        cur.execute(
            """
            select 1 from suppression
            where brand_scope = any(%(scopes)s)
              and ((email is not null and lower(email) = lower(%(email)s))
                or (domain is not null and lower(domain) = %(domain)s))
            limit 1
            """,
            {"scopes": scopes, "email": email, "domain": _domain_of(email)},
        )
        return cur.fetchone() is not None


def suppress(
    conn: psycopg.Connection,
    *,
    reason: str,
    email: str | None = None,
    domain: str | None = None,
    brand_scope: str = "all",
) -> None:
    """Add an email or domain to the suppression list, idempotently."""
    if not email and not domain:
        raise ValueError("suppress needs an email or a domain")
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into suppression (email, domain, reason, brand_scope)
            values (%s, %s, %s, %s)
            on conflict do nothing
            """,
            (email, domain, reason, brand_scope),
        )
