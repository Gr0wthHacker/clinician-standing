"""Writes for ``POST /v1/roster``: the one place the API writes.

The lookup store (:mod:`.store`) opens every connection read-only and points at
a read-only role. Roster intake needs a write, so it has its own store and its
own credential, ``API_ROSTER_DATABASE_URL``, naming the ``app_roster_api`` role
from ``0019_roster_intake.sql``. That role can reach ``roster_intake`` and no
other table, so a bug here cannot touch the evidence store or the credential
tables.

Nothing in this module logs a submission. Errors carry the exception type only.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol, cast

import psycopg

from .models import RosterOutcome, RosterReviewStatus, RosterSubmission
from .store import StoreUnavailable

__all__ = [
    "MemoryRosterStore",
    "PostgresRosterStore",
    "RosterEntryClosed",
    "RosterStore",
    "RosterWrite",
]


class RosterEntryClosed(RuntimeError):
    """The (source_system, external_id) row exists but was closed internally."""


@dataclass(frozen=True)
class RosterWrite:
    id: str
    outcome: RosterOutcome
    review_status: RosterReviewStatus
    received_at: datetime
    updated_at: datetime


class RosterStore(Protocol):
    def upsert(self, submission: RosterSubmission, api_key_id: str, now: datetime) -> RosterWrite:
        """Insert or update the row for ``(source_system, external_id)``."""
        ...


def _row_values(submission: RosterSubmission, api_key_id: str, now: datetime) -> dict[str, Any]:
    c = submission.clinician
    return {
        "source_system": submission.source_system,
        "external_id": submission.external_id,
        "api_key_id": api_key_id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "npi": c.npi,
        "credential": c.credential,
        "licenses": json.dumps([lic.model_dump(mode="json") for lic in submission.licenses]),
        "states": list(submission.states),
        "employer_name": submission.employer.name,
        "employer_org_pac_id": submission.employer.org_pac_id,
        "employment_status": submission.employment_status,
        "placed_on": submission.placed_on,
        "payload_sha256": submission.digest(),
        "now": now,
    }


_UPSERT_SQL = """
insert into roster_intake (
    source_system, external_id, api_key_id, first_name, last_name, npi, credential,
    licenses, states, employer_name, employer_org_pac_id, employment_status, placed_on,
    payload_sha256
)
values (
    %(source_system)s, %(external_id)s, %(api_key_id)s, %(first_name)s, %(last_name)s,
    %(npi)s, %(credential)s, %(licenses)s::jsonb, %(states)s, %(employer_name)s,
    %(employer_org_pac_id)s, %(employment_status)s, %(placed_on)s, %(payload_sha256)s
)
on conflict (source_system, external_id) do update set
    api_key_id          = excluded.api_key_id,
    first_name          = excluded.first_name,
    last_name           = excluded.last_name,
    npi                 = excluded.npi,
    credential          = excluded.credential,
    licenses            = excluded.licenses,
    states              = excluded.states,
    employer_name       = excluded.employer_name,
    employer_org_pac_id = excluded.employer_org_pac_id,
    employment_status   = excluded.employment_status,
    placed_on           = excluded.placed_on,
    payload_sha256      = excluded.payload_sha256,
    updated_at          = %(now)s
where roster_intake.payload_sha256 is distinct from excluded.payload_sha256
  and roster_intake.deleted_at is null
returning id, (xmax = 0) as inserted, review_status, received_at, updated_at
"""

_EXISTING_SQL = """
select id, review_status, received_at, updated_at
from roster_intake
where source_system = %(source_system)s and external_id = %(external_id)s
  and deleted_at is null
"""

ConnectionFactory = Callable[[], AbstractContextManager[psycopg.Connection]]


class PostgresRosterStore:
    """One short read-write connection per call, committed on success.

    Args:
        conninfo: libpq URI for the ``app_roster_api`` role.
        connection_factory: Yields an open connection the caller owns; the
            database tests pass one inside a transaction they roll back.
    """

    def __init__(
        self,
        conninfo: str | None = None,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if conninfo is None and connection_factory is None:
            raise ValueError("PostgresRosterStore needs a conninfo or a connection_factory")
        self._conninfo = conninfo
        self._factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        try:
            if self._factory is not None:
                with self._factory() as conn:
                    yield conn
                return
            assert self._conninfo is not None
            with psycopg.connect(self._conninfo, connect_timeout=10) as conn:
                yield conn  # the context manager commits on success, rolls back on error
        except psycopg.Error as exc:
            raise StoreUnavailable(f"database error: {type(exc).__name__}") from exc

    def upsert(self, submission: RosterSubmission, api_key_id: str, now: datetime) -> RosterWrite:
        values = _row_values(submission, api_key_id, now)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(_UPSERT_SQL, values)
            row = cur.fetchone()
            if row is not None:
                return RosterWrite(
                    id=str(row[0]),
                    outcome="created" if row[1] else "updated",
                    review_status=cast(RosterReviewStatus, row[2]),
                    received_at=row[3],
                    updated_at=row[4],
                )
            cur.execute(_EXISTING_SQL, values)
            existing = cur.fetchone()
        if existing is None:
            raise RosterEntryClosed(submission.external_id)
        return RosterWrite(
            id=str(existing[0]),
            outcome="unchanged",
            review_status=cast(RosterReviewStatus, existing[1]),
            received_at=existing[2],
            updated_at=existing[3],
        )


@dataclass
class _MemoryRow:
    write: RosterWrite
    digest: str
    values: dict[str, Any]
    closed: bool = False


class MemoryRosterStore:
    """In-memory roster intake with the same idempotency rules as Postgres."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], _MemoryRow] = {}
        self._lock = threading.Lock()

    def upsert(self, submission: RosterSubmission, api_key_id: str, now: datetime) -> RosterWrite:
        key = (submission.source_system, submission.external_id)
        values = _row_values(submission, api_key_id, now)
        digest = values["payload_sha256"]
        with self._lock:
            row = self._rows.get(key)
            if row is None:
                write = RosterWrite(
                    id=str(uuid.uuid4()),
                    outcome="created",
                    review_status="pending",
                    received_at=now,
                    updated_at=now,
                )
                self._rows[key] = _MemoryRow(write=write, digest=digest, values=values)
                return write
            if row.closed:
                raise RosterEntryClosed(submission.external_id)
            if row.digest == digest:
                return replace(row.write, outcome="unchanged")
            row.write = replace(row.write, outcome="updated", updated_at=now)
            row.digest = digest
            row.values = values
            return row.write

    def close(self, source_system: str, external_id: str) -> None:
        """Mark a row closed, as an internal soft delete would. Tests use it."""
        self._rows[(source_system, external_id)].closed = True

    def get(self, source_system: str, external_id: str) -> dict[str, Any] | None:
        row = self._rows.get((source_system, external_id))
        return dict(row.values) if row is not None else None
