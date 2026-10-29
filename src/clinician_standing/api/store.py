"""Data access for the standing API.

Two implementations of one small protocol:

* :class:`PostgresStore` reads the shared Supabase database the ingest writes.
  Every connection it opens is set read-only, so a bug in this module cannot
  write a row even when the configured role could.
* :class:`MemoryStore` holds records in memory. The test suite builds one from
  an obviously synthetic fixture, and it is the natural backing for a future
  sandbox key that returns deterministic answers.

Both return the same frozen record types, so everything above this module is
tested once, without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

import psycopg

__all__ = [
    "ClinicianRecord",
    "LicenseRecord",
    "MemoryStore",
    "PossibleExclusionRecord",
    "PostgresStore",
    "SanctionRecord",
    "SourceRecord",
    "StandingStore",
    "StoreUnavailable",
]


class StoreUnavailable(RuntimeError):
    """The backing database could not answer. Surfaces as HTTP 503."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRecord:
    """One row of the source registry plus its newest evidence row."""

    key: str
    display_name: str | None
    kind: str | None
    cadence: str | None
    freshness_sla_days: int
    enabled: bool
    is_primary_source: bool
    terms_url: str | None
    fetched_at: datetime | None
    freshness_expires_at: datetime | None
    parsed: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ingested(self) -> bool:
        """True when at least one evidence row exists for this source."""
        return self.fetched_at is not None


@dataclass(frozen=True)
class SanctionRecord:
    """One ``sanctions`` row matched to a clinician, with its evidence."""

    source: str
    action_type: str | None
    action_date: date | None
    description: str | None
    reinstated_date: date | None
    match_confidence: float | None
    evidence_source_key: str | None
    evidence_fetched_at: datetime | None


@dataclass(frozen=True)
class PossibleExclusionRecord:
    """One live ``leie_npi_candidates`` row for a clinician's NPI (0017)."""

    review_status: str
    match_basis: str
    match_confidence: float
    match_detail: Mapping[str, Any]
    candidate_count: int
    leie_last_name: str
    leie_first_name: str | None
    leie_middle_name: str | None
    leie_state: str
    leie_specialty: str | None
    exclusion_type: str | None
    exclusion_date: date | None
    reinstatement_date: date | None
    evidence_source_key: str | None
    evidence_fetched_at: datetime | None


@dataclass(frozen=True)
class LicenseRecord:
    """One ``licenses`` row, with the source that asserted it."""

    state: str
    license_type: str
    license_number: str | None
    status: str
    issue_date: date | None
    expiry_date: date | None
    is_compact: bool
    compact_home_state: str | None
    verified_at: datetime
    evidence_source_key: str | None
    evidence_fetched_at: datetime | None
    discipline_reported: bool | None


@dataclass(frozen=True)
class ClinicianRecord:
    """A clinician as the ingested data holds them."""

    npi: str
    first_name: str | None
    middle_name: str | None
    last_name: str | None
    suffix: str | None
    credential: str | None
    clinician_type: str
    primary_specialty: str | None
    practice_states: tuple[str, ...] = ()
    sanctions: tuple[SanctionRecord, ...] = ()
    licenses: tuple[LicenseRecord, ...] = ()
    possible_exclusions: tuple[PossibleExclusionRecord, ...] = ()


class StandingStore(Protocol):
    """What the API needs from a data source."""

    def list_sources(self) -> list[SourceRecord]:
        """Every registered source with its newest evidence row."""
        ...

    def get_by_npi(self, npi: str) -> ClinicianRecord | None:
        """The clinician carrying ``npi``, or None."""
        ...

    def find_by_name(
        self, last_name: str, first_name: str | None, state: str, limit: int
    ) -> list[ClinicianRecord]:
        """Clinicians whose name matches exactly and who are tied to ``state``.

        ``last_name`` and ``first_name`` arrive upper-cased and whitespace-
        normalized. A clinician is tied to a state through an active affiliation
        with a practice located there, or through a license issued there.
        """
        ...


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

_SOURCES_SQL = """
select s.key, s.display_name, s.kind, s.cadence, s.freshness_sla_days, s.enabled,
       s.is_primary_source, s.terms_url, e.fetched_at, e.freshness_expires_at, e.parsed
from sources s
left join lateral (
    select fetched_at, freshness_expires_at, parsed
    from evidence
    where source_key = s.key and deleted_at is null
    -- A connector that also writes per-match evidence (oig_leie) stamps it with
    -- the same fetched_at as the file row; the file row carries the coverage
    -- counts the notes read, so it wins the tie.
    order by fetched_at desc, coalesce(match_keys ->> 'method', '') = 'bulk_file' desc
    limit 1
) e on true
where s.deleted_at is null
order by s.key
"""

_CLINICIAN_COLUMNS = """
c.id, c.npi, c.first_name, c.middle_name, c.last_name, c.suffix, c.credential,
c.clinician_type, c.primary_specialty
"""

_BY_NPI_SQL = f"""
select {_CLINICIAN_COLUMNS}
from clinicians c
where c.npi = %(npi)s and c.deleted_at is null
"""

_BY_NAME_SQL = f"""
select {_CLINICIAN_COLUMNS}
from clinicians c
where c.deleted_at is null
  and upper(c.last_name) = %(last_name)s
  and (%(first_name)s::text is null or upper(c.first_name) = %(first_name)s)
  and (
    exists (
      select 1
      from affiliations a
      join practices p on p.id = a.practice_id and p.deleted_at is null
      where a.clinician_id = c.id and a.deleted_at is null and a.end_date is null
        and p.state = %(state)s
    )
    or exists (
      select 1 from licenses l
      where l.clinician_id = c.id and l.deleted_at is null and l.state = %(state)s
    )
  )
order by c.last_name, c.first_name nulls last, c.npi
limit %(limit)s
"""

_PRACTICE_STATES_SQL = """
select distinct a.clinician_id, p.state
from affiliations a
join practices p on p.id = a.practice_id and p.deleted_at is null
where a.clinician_id = any(%(ids)s) and a.deleted_at is null and a.end_date is null
  and p.state is not null
order by 2
"""

_SANCTIONS_SQL = """
select s.clinician_id, s.source, s.action_type, s.action_date, s.description,
       s.reinstated_date, s.match_confidence, ev.source_key, ev.fetched_at
from sanctions s
left join evidence ev on ev.id = s.evidence_id
where s.clinician_id = any(%(ids)s) and s.deleted_at is null
order by s.action_date desc nulls last
"""

# Rejected candidates and candidates the latest LEIE run no longer produced are
# not shown. Highest confidence first.
_POSSIBLE_EXCLUSIONS_SQL = """
select k.npi, k.review_status, k.match_basis, k.match_confidence, k.match_detail,
       k.candidate_count, k.leie_last_name, k.leie_first_name, k.leie_middle_name,
       k.leie_state, k.leie_specialty, k.exclusion_type, k.exclusion_date,
       k.reinstatement_date, ev.source_key, ev.fetched_at
from leie_npi_candidates k
left join evidence ev on ev.id = k.leie_evidence_id
where k.npi = any(%(npis)s)
  and k.superseded_at is null
  and k.review_status <> 'rejected'
order by k.match_confidence desc, k.exclusion_date desc nulls last, k.leie_key
"""

_LICENSES_SQL = """
select l.clinician_id, l.state, l.license_type, l.license_number, l.status, l.issue_date,
       l.expiry_date, coalesce(l.is_compact, false), l.compact_home_state, l.verified_at,
       ev.source_key, ev.fetched_at, (ev.match_keys ->> 'has_discipline')::boolean
from licenses l
left join evidence ev on ev.id = l.evidence_id
where l.clinician_id = any(%(ids)s) and l.deleted_at is null
order by l.state, l.license_type, l.license_number nulls last
"""


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


ConnectionFactory = Callable[[], AbstractContextManager[psycopg.Connection]]


class PostgresStore:
    """Reads the shared database, one short read-only connection per call.

    Args:
        conninfo: libpq URI. Used when ``connection_factory`` is not given.
        connection_factory: Yields an open connection; the caller keeps
            ownership. The database tests pass one that hands back a
            connection holding seeded rows inside an open transaction.
    """

    def __init__(
        self,
        conninfo: str | None = None,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if conninfo is None and connection_factory is None:
            raise ValueError("PostgresStore needs a conninfo or a connection_factory")
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
            conn = psycopg.connect(self._conninfo, connect_timeout=10)
            try:
                conn.read_only = True
                yield conn
            finally:
                conn.rollback()
                conn.close()
        except psycopg.Error as exc:
            raise StoreUnavailable(f"database error: {type(exc).__name__}") from exc

    @staticmethod
    def _rows(conn: psycopg.Connection, sql: str, params: Mapping[str, Any]) -> list[Any]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def list_sources(self) -> list[SourceRecord]:
        with self._connection() as conn:
            rows = self._rows(conn, _SOURCES_SQL, {})
        return [
            SourceRecord(
                key=r[0],
                display_name=r[1],
                kind=r[2],
                cadence=r[3],
                freshness_sla_days=int(r[4]),
                enabled=bool(r[5]),
                is_primary_source=bool(r[6]),
                terms_url=r[7],
                fetched_at=r[8],
                freshness_expires_at=r[9],
                parsed=r[10] if isinstance(r[10], dict) else {},
            )
            for r in rows
        ]

    def get_by_npi(self, npi: str) -> ClinicianRecord | None:
        with self._connection() as conn:
            rows = self._rows(conn, _BY_NPI_SQL, {"npi": npi})
            found = self._hydrate(conn, rows)
        return found[0] if found else None

    def find_by_name(
        self, last_name: str, first_name: str | None, state: str, limit: int
    ) -> list[ClinicianRecord]:
        params = {
            "last_name": last_name,
            "first_name": first_name,
            "state": state,
            "limit": limit,
        }
        with self._connection() as conn:
            rows = self._rows(conn, _BY_NAME_SQL, params)
            return self._hydrate(conn, rows)

    def _hydrate(self, conn: psycopg.Connection, rows: Sequence[Any]) -> list[ClinicianRecord]:
        if not rows:
            return []
        ids = [r[0] for r in rows]
        states: dict[Any, list[str]] = {}
        for cid, state in self._rows(conn, _PRACTICE_STATES_SQL, {"ids": ids}):
            states.setdefault(cid, []).append(state)
        sanctions: dict[Any, list[SanctionRecord]] = {}
        for r in self._rows(conn, _SANCTIONS_SQL, {"ids": ids}):
            sanctions.setdefault(r[0], []).append(
                SanctionRecord(
                    source=r[1],
                    action_type=r[2],
                    action_date=r[3],
                    description=r[4],
                    reinstated_date=r[5],
                    match_confidence=_float(r[6]),
                    evidence_source_key=r[7],
                    evidence_fetched_at=r[8],
                )
            )
        licenses: dict[Any, list[LicenseRecord]] = {}
        for r in self._rows(conn, _LICENSES_SQL, {"ids": ids}):
            licenses.setdefault(r[0], []).append(
                LicenseRecord(
                    state=r[1],
                    license_type=r[2],
                    license_number=r[3],
                    status=r[4],
                    issue_date=r[5],
                    expiry_date=r[6],
                    is_compact=bool(r[7]),
                    compact_home_state=r[8],
                    verified_at=r[9],
                    evidence_source_key=r[10],
                    evidence_fetched_at=r[11],
                    discipline_reported=r[12],
                )
            )
        possible: dict[str, list[PossibleExclusionRecord]] = {}
        for r in self._rows(conn, _POSSIBLE_EXCLUSIONS_SQL, {"npis": [r[1] for r in rows]}):
            possible.setdefault(r[0], []).append(
                PossibleExclusionRecord(
                    review_status=r[1],
                    match_basis=r[2],
                    match_confidence=float(r[3]),
                    match_detail=r[4] if isinstance(r[4], dict) else {},
                    candidate_count=int(r[5]),
                    leie_last_name=r[6],
                    leie_first_name=r[7],
                    leie_middle_name=r[8],
                    leie_state=r[9],
                    leie_specialty=r[10],
                    exclusion_type=r[11],
                    exclusion_date=r[12],
                    reinstatement_date=r[13],
                    evidence_source_key=r[14],
                    evidence_fetched_at=r[15],
                )
            )
        return [
            ClinicianRecord(
                npi=r[1],
                first_name=r[2],
                middle_name=r[3],
                last_name=r[4],
                suffix=r[5],
                credential=r[6],
                clinician_type=r[7],
                primary_specialty=r[8],
                practice_states=tuple(states.get(r[0], ())),
                sanctions=tuple(sanctions.get(r[0], ())),
                licenses=tuple(licenses.get(r[0], ())),
                possible_exclusions=tuple(possible.get(r[1], ())),
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# In memory
# ---------------------------------------------------------------------------


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else value


def _datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


class MemoryStore:
    """Holds records in memory. Matching rules mirror :class:`PostgresStore`."""

    def __init__(
        self, sources: Sequence[SourceRecord], clinicians: Sequence[ClinicianRecord]
    ) -> None:
        self._sources = sorted(sources, key=lambda s: s.key)
        self._clinicians = list(clinicians)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MemoryStore:
        """Build a store from plain JSON-shaped data (ISO date strings)."""
        sources = [
            SourceRecord(
                key=s["key"],
                display_name=s.get("display_name"),
                kind=s.get("kind"),
                cadence=s.get("cadence"),
                freshness_sla_days=int(s["freshness_sla_days"]),
                enabled=bool(s.get("enabled", True)),
                is_primary_source=bool(s.get("is_primary_source", False)),
                terms_url=s.get("terms_url"),
                fetched_at=_datetime(s.get("fetched_at")),
                freshness_expires_at=_datetime(s.get("freshness_expires_at")),
                parsed=s.get("parsed") or {},
            )
            for s in data.get("sources", [])
        ]
        clinicians = []
        for c in data.get("clinicians", []):
            sanctions = tuple(
                SanctionRecord(
                    source=x["source"],
                    action_type=x.get("action_type"),
                    action_date=_date(x.get("action_date")),
                    description=x.get("description"),
                    reinstated_date=_date(x.get("reinstated_date")),
                    match_confidence=_float(x.get("match_confidence")),
                    evidence_source_key=x.get("evidence_source_key"),
                    evidence_fetched_at=_datetime(x.get("evidence_fetched_at")),
                )
                for x in c.get("sanctions", [])
            )
            licenses = tuple(
                LicenseRecord(
                    state=x["state"],
                    license_type=x["license_type"],
                    license_number=x.get("license_number"),
                    status=x["status"],
                    issue_date=_date(x.get("issue_date")),
                    expiry_date=_date(x.get("expiry_date")),
                    is_compact=bool(x.get("is_compact", False)),
                    compact_home_state=x.get("compact_home_state"),
                    verified_at=_datetime(x["verified_at"]),  # type: ignore[arg-type]
                    evidence_source_key=x.get("evidence_source_key"),
                    evidence_fetched_at=_datetime(x.get("evidence_fetched_at")),
                    discipline_reported=x.get("discipline_reported"),
                )
                for x in c.get("licenses", [])
            )
            possible = tuple(
                PossibleExclusionRecord(
                    review_status=x.get("review_status", "needs_review"),
                    match_basis=x.get("match_basis", "name_state"),
                    match_confidence=float(x["match_confidence"]),
                    match_detail=x.get("match_detail") or {},
                    candidate_count=int(x.get("candidate_count", 1)),
                    leie_last_name=x["leie_last_name"],
                    leie_first_name=x.get("leie_first_name"),
                    leie_middle_name=x.get("leie_middle_name"),
                    leie_state=x["leie_state"],
                    leie_specialty=x.get("leie_specialty"),
                    exclusion_type=x.get("exclusion_type"),
                    exclusion_date=_date(x.get("exclusion_date")),
                    reinstatement_date=_date(x.get("reinstatement_date")),
                    evidence_source_key=x.get("evidence_source_key"),
                    evidence_fetched_at=_datetime(x.get("evidence_fetched_at")),
                )
                for x in c.get("possible_exclusions", [])
                if x.get("review_status", "needs_review") != "rejected"
                and not x.get("superseded_at")
            )
            clinicians.append(
                ClinicianRecord(
                    npi=c["npi"],
                    first_name=c.get("first_name"),
                    middle_name=c.get("middle_name"),
                    last_name=c.get("last_name"),
                    suffix=c.get("suffix"),
                    credential=c.get("credential"),
                    clinician_type=c["clinician_type"],
                    primary_specialty=c.get("primary_specialty"),
                    practice_states=tuple(sorted(c.get("practice_states", []))),
                    sanctions=sanctions,
                    licenses=licenses,
                    possible_exclusions=possible,
                )
            )
        return cls(sources, clinicians)

    def list_sources(self) -> list[SourceRecord]:
        return list(self._sources)

    def get_by_npi(self, npi: str) -> ClinicianRecord | None:
        return next((c for c in self._clinicians if c.npi == npi), None)

    def find_by_name(
        self, last_name: str, first_name: str | None, state: str, limit: int
    ) -> list[ClinicianRecord]:
        def tied(c: ClinicianRecord) -> bool:
            return state in c.practice_states or any(lic.state == state for lic in c.licenses)

        hits = [
            c
            for c in self._clinicians
            if (c.last_name or "").upper() == last_name
            and (first_name is None or (c.first_name or "").upper() == first_name)
            and tied(c)
        ]
        hits.sort(key=lambda c: (c.last_name or "", c.first_name or "", c.npi))
        return hits[:limit]
