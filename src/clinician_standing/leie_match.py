"""Propose NPI candidates for OIG LEIE rows that carry no NPI.

About 90% of LEIE rows have no NPI, so the NPI screen in ``oig_leie.py`` cannot
see them. NPPES (``nppes_providers``, 0016) names every individual NPI with a
practice state and the license states the provider reported, which is enough to
propose who an LEIE row might be. It is not enough to say who it is: NPPES has
no date of birth, and same-name clinicians in one state are common.

So this module produces candidates, never exclusions:

* nothing here writes ``sanctions``. Only an NPI match does.
* every confidence is below :data:`MAX_CONFIDENCE`, which is below 1.0, and the
  table enforces ``< 1`` with a CHECK. 1.0 means an NPI match (PRD 8.1).
* candidates land in ``leie_npi_candidates`` as ``needs_review``, and the API
  shows them as possible matches that need a person to look.

Matching, for one LEIE row (individuals only, with a state, without an NPI):

1. **Block** on the surname key (:func:`name_key`, mirrored in SQL as
   ``app.name_key``) against individual NPIs whose practice state, or any
   self-reported license state, equals the LEIE state.
2. **Compare first names**: exact, a prefix of at least three letters
   ("CHRIS" / "CHRISTOPHER"), or an initial. Anything else is not a candidate.
3. **Compare middle names**: if both sides carry one and the initials differ,
   not a candidate. Agreeing initials raise the score; a missing side is neutral.
4. **Score** from :data:`BASE_CONFIDENCE`, then divide by the number of
   candidates the row produced, so three same-name NPIs share the weight one
   would carry. More than :data:`MAX_CANDIDATES_PER_ROW` and the row is recorded
   as too ambiguous, with no candidates written.

The base scores are ordering, not measured probabilities. Nobody has labeled a
sample yet; until someone does, read them as "which candidate to look at first".
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

__all__ = [
    "ACCENTS_FROM",
    "ACCENTS_TO",
    "BASE_CONFIDENCE",
    "MAX_CANDIDATES_PER_ROW",
    "MAX_CONFIDENCE",
    "Candidate",
    "LeieRow",
    "MatchSummary",
    "NppesPerson",
    "leie_key",
    "match_row",
    "name_key",
    "record_candidates",
]

#: Accent folding, character for character. ``app.name_key`` in
#: 0018_leie_npi_candidates.sql uses these exact literals; a test checks.
ACCENTS_FROM = "ÀÁÂÃÄÅàáâãäåÇçÈÉÊËèéêëÌÍÎÏìíîïÑñÒÓÔÕÖØòóôõöøÙÚÛÜùúûüÝýÿ"
ACCENTS_TO = "AAAAAAaaaaaaCcEEEEeeeeIIIIiiiiNnOOOOOOooooooUUUUuuuuYyy"
_FOLD = str.maketrans(ACCENTS_FROM, ACCENTS_TO)
_NON_LETTERS = re.compile(r"[^A-Z]+")
_SUFFIXES = re.compile(r"( (JR|SR|II|III|IV))+$")

FirstNameMatch = Literal["exact", "prefix", "initial"]
MiddleNameMatch = Literal["agrees", "unknown"]
StateMatch = Literal["practice", "license", "practice_and_license"]

#: Score before the ambiguity split, by (first name, middle name) agreement.
BASE_CONFIDENCE: Mapping[tuple[FirstNameMatch, MiddleNameMatch], float] = {
    ("exact", "agrees"): 0.85,
    ("exact", "unknown"): 0.70,
    ("prefix", "agrees"): 0.60,
    ("prefix", "unknown"): 0.50,
    ("initial", "agrees"): 0.45,
    ("initial", "unknown"): 0.35,
}

#: No name match may score higher than this. The table CHECK is ``< 1``.
MAX_CONFIDENCE = 0.85

#: A row with more candidates than this is recorded as too ambiguous to propose.
MAX_CANDIDATES_PER_ROW = 10

#: Floor for a stored confidence; the CHECK requires ``> 0``.
_MIN_CONFIDENCE = 0.001

assert max(BASE_CONFIDENCE.values()) <= MAX_CONFIDENCE < 1.0


def _ascii_upper(value: str) -> str:
    """Upper-case ASCII letters only, as Postgres ``upper()`` does in every locale."""
    return "".join(c.upper() if c.isascii() else c for c in value)


def name_key(raw: str | None) -> str | None:
    """Normalize a name for blocking and comparison. Mirrors ``app.name_key``.

    Fold the common Latin accents, upper-case ASCII, collapse every run of
    non-letters to one space, trim, drop trailing JR/SR/II/III/IV, remove the
    spaces.

    Args:
        raw: A surname or given name as published.

    Returns:
        The key, or None when nothing is left.
    """
    folded = _ascii_upper((raw or "").translate(_FOLD))
    spaced = _NON_LETTERS.sub(" ", folded).strip()
    key = _SUFFIXES.sub("", spaced).replace(" ", "")
    return key or None


def leie_key(identity_key: str) -> str:
    """Stable id of an LEIE row: sha256 hex of the connector's identity key."""
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LeieRow:
    """The parts of an LEIE row that matching and review need."""

    leie_key: str
    last_name: str
    first_name: str | None
    middle_name: str | None
    state: str
    general_category: str | None = None
    specialty: str | None = None
    exclusion_type: str | None = None
    exclusion_date: date | None = None
    reinstatement_date: date | None = None
    waiver_date: date | None = None


@dataclass(frozen=True)
class NppesPerson:
    """An individual NPI as ``nppes_providers`` holds it."""

    npi: str
    last_name: str | None
    first_name: str | None
    middle_name: str | None
    practice_state: str | None
    license_states: tuple[str, ...] = ()
    is_active: bool | None = None


@dataclass(frozen=True)
class Candidate:
    """One proposed LEIE row to NPI link."""

    leie: LeieRow
    person: NppesPerson
    first_name: FirstNameMatch
    middle_name: MiddleNameMatch
    state: StateMatch
    base_confidence: float
    confidence: float
    candidate_count: int

    @property
    def detail(self) -> dict[str, Any]:
        """The ``match_detail`` JSON stored with the row and shown by the API."""
        return {
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "state": self.state,
            "base_confidence": self.base_confidence,
        }


def _first_name_match(leie: str | None, nppes: str | None) -> FirstNameMatch | None:
    a, b = name_key(leie), name_key(nppes)
    if not a or not b:
        return None
    if a == b:
        return "exact"
    short, long_ = sorted((a, b), key=len)
    if len(short) == 1:
        return "initial" if long_.startswith(short) else None
    if len(short) >= 3 and long_.startswith(short):
        return "prefix"
    return None


def _middle_name_match(leie: str | None, nppes: str | None) -> MiddleNameMatch | None:
    a, b = name_key(leie), name_key(nppes)
    if not a or not b:
        return "unknown"
    return "agrees" if a[0] == b[0] else None


def _state_match(state: str, person: NppesPerson) -> StateMatch | None:
    practice = (person.practice_state or "").upper() == state
    license_ = state in {s.upper() for s in person.license_states}
    if practice and license_:
        return "practice_and_license"
    if practice:
        return "practice"
    if license_:
        return "license"
    return None


def match_row(row: LeieRow, people: Iterable[NppesPerson]) -> tuple[list[Candidate], bool]:
    """Score every NPPES person against one LEIE row.

    Args:
        row: An individual LEIE row with a state and no NPI.
        people: NPPES individuals already blocked on surname key and state. The
            surname and state are checked again here, so a looser block is safe.

    Returns:
        ``(candidates, too_ambiguous)``. ``candidates`` is empty when nothing
        matched or when more than :data:`MAX_CANDIDATES_PER_ROW` did, which is
        the case ``too_ambiguous`` flags. Candidates are ordered by confidence,
        then NPI.
    """
    surname = name_key(row.last_name)
    state = row.state.upper()
    scored: list[tuple[NppesPerson, FirstNameMatch, MiddleNameMatch, StateMatch, float]] = []
    seen: set[str] = set()
    for person in people:
        if person.npi in seen or not surname or name_key(person.last_name) != surname:
            continue
        state_match = _state_match(state, person)
        if state_match is None:
            continue
        first = _first_name_match(row.first_name, person.first_name)
        if first is None:
            continue
        middle = _middle_name_match(row.middle_name, person.middle_name)
        if middle is None:
            continue
        seen.add(person.npi)
        scored.append((person, first, middle, state_match, BASE_CONFIDENCE[(first, middle)]))

    if len(scored) > MAX_CANDIDATES_PER_ROW:
        return [], True
    count = len(scored)
    candidates = [
        Candidate(
            leie=row,
            person=person,
            first_name=first,
            middle_name=middle,
            state=state_match,
            base_confidence=base,
            confidence=max(_MIN_CONFIDENCE, round(min(base, MAX_CONFIDENCE) / count, 3)),
            candidate_count=count,
        )
        for person, first, middle, state_match, base in scored
    ]
    candidates.sort(key=lambda c: (-c.confidence, c.person.npi))
    return candidates, False


# ---------------------------------------------------------------------------
# Database step
# ---------------------------------------------------------------------------


@dataclass
class MatchSummary:
    """What one matching pass did, for the LEIE evidence row and the run log."""

    nppes_rows_available: bool = False
    rows_eligible: int = 0
    rows_with_candidates: int = 0
    rows_too_ambiguous: int = 0
    candidates_written: int = 0
    candidates_superseded: int = 0
    by_basis: dict[str, int] = field(default_factory=dict)

    def as_parsed(self) -> dict[str, Any]:
        """Keys merged into the LEIE file evidence ``parsed`` JSON."""
        return {
            "name_state_matching_ran": self.nppes_rows_available,
            "rows_without_npi_eligible": self.rows_eligible,
            "rows_without_npi_with_candidates": self.rows_with_candidates,
            "rows_without_npi_too_ambiguous": self.rows_too_ambiguous,
            "name_state_candidates_written": self.candidates_written,
            "name_state_candidates_superseded": self.candidates_superseded,
        }


#: The staged LEIE rows the name step looks at: individuals, with a state,
#: without an NPI. ``stg_oig_leie_named`` is built from ``stg_oig_leie`` by
#: :func:`record_candidates`.
_CREATE_NAMED = """
create temporary table stg_oig_leie_named on commit drop as
select leie_key, last_name, first_name, middle_name, state, general_category,
       specialty, exclusion_type, exclusion_date, reinstatement_date, waiver_date,
       app.name_key(last_name) as last_key,
       left(app.name_key(first_name), 1) as first_initial
from stg_oig_leie
where npi is null
  and last_name is not null
  and app.name_key(first_name) is not null
  and state ~ '^[A-Z]{2}$'
"""

#: Blocked pairs. Surname key, first initial and state are checked in SQL so
#: the pair set stays small; the full first and middle name comparison is in
#: Python (:func:`match_row`).
_SELECT_PAIRS = """
select s.leie_key, s.last_name, s.first_name, s.middle_name, s.state,
       s.general_category, s.specialty, s.exclusion_type, s.exclusion_date,
       s.reinstatement_date, s.waiver_date,
       n.npi, n.last_name, n.first_name, n.middle_name, n.practice_state,
       coalesce(
         (select array_agg(distinct upper(t ->> 'license_state'))
            from jsonb_array_elements(n.taxonomies) t
           where coalesce(t ->> 'license_state', '') <> ''),
         '{}'::text[]),
       n.is_active
from stg_oig_leie_named s
join nppes_providers n
  on n.entity_type = 1
 and app.name_key(n.last_name) = s.last_key
 and left(app.name_key(n.first_name), 1) = s.first_initial
 and (
   upper(n.practice_state) = s.state
   or n.taxonomies @> jsonb_build_array(jsonb_build_object('license_state', s.state))
 )
order by s.leie_key, n.npi
"""

_UPSERT_CANDIDATE = """
insert into leie_npi_candidates (
    leie_key, npi, leie_last_name, leie_first_name, leie_middle_name, leie_state,
    leie_general_category, leie_specialty, exclusion_type, exclusion_date,
    reinstatement_date, waiver_date, nppes_last_name, nppes_first_name,
    nppes_middle_name, nppes_practice_state, nppes_is_active, match_basis,
    match_detail, match_confidence, candidate_count, leie_evidence_id,
    last_seen_at, superseded_at, updated_at
) values (
    %(leie_key)s, %(npi)s, %(leie_last_name)s, %(leie_first_name)s, %(leie_middle_name)s,
    %(leie_state)s, %(leie_general_category)s, %(leie_specialty)s, %(exclusion_type)s,
    %(exclusion_date)s, %(reinstatement_date)s, %(waiver_date)s, %(nppes_last_name)s,
    %(nppes_first_name)s, %(nppes_middle_name)s, %(nppes_practice_state)s,
    %(nppes_is_active)s, 'name_state', %(match_detail)s::jsonb, %(match_confidence)s,
    %(candidate_count)s, %(leie_evidence_id)s, %(run_started)s, null, now()
)
on conflict (leie_key, npi) do update set
    leie_last_name = excluded.leie_last_name,
    leie_first_name = excluded.leie_first_name,
    leie_middle_name = excluded.leie_middle_name,
    leie_state = excluded.leie_state,
    leie_general_category = excluded.leie_general_category,
    leie_specialty = excluded.leie_specialty,
    exclusion_type = excluded.exclusion_type,
    exclusion_date = excluded.exclusion_date,
    reinstatement_date = excluded.reinstatement_date,
    waiver_date = excluded.waiver_date,
    nppes_last_name = excluded.nppes_last_name,
    nppes_first_name = excluded.nppes_first_name,
    nppes_middle_name = excluded.nppes_middle_name,
    nppes_practice_state = excluded.nppes_practice_state,
    nppes_is_active = excluded.nppes_is_active,
    match_detail = excluded.match_detail,
    match_confidence = excluded.match_confidence,
    candidate_count = excluded.candidate_count,
    leie_evidence_id = excluded.leie_evidence_id,
    last_seen_at = excluded.last_seen_at,
    superseded_at = null,
    updated_at = now()
"""

# A candidate this pass did not produce. review_status is kept: a rejection
# must survive the row dropping out and coming back.
_SUPERSEDE = """
update leie_npi_candidates
   set superseded_at = now(), updated_at = now()
 where superseded_at is null
   and last_seen_at < %(run_started)s
"""


#: Rows per server-side fetch and per candidate write batch.
_PAIR_BATCH = 5000


def _scalar(cur: Any) -> Any:
    row = cur.fetchone()
    if row is None:  # pragma: no cover - aggregate and now() always return a row
        raise RuntimeError("expected one row")
    return row[0]


def _iter_pairs(rows: Iterable[Sequence[Any]]) -> Iterator[tuple[LeieRow, list[NppesPerson]]]:
    """Group ``_SELECT_PAIRS`` output (ordered by leie_key) into one block per LEIE row."""
    current: LeieRow | None = None
    people: list[NppesPerson] = []
    for r in rows:
        if current is None or r[0] != current.leie_key:
            if current is not None:
                yield current, people
            current = LeieRow(
                leie_key=r[0],
                last_name=r[1],
                first_name=r[2],
                middle_name=r[3],
                state=r[4],
                general_category=r[5],
                specialty=r[6],
                exclusion_type=r[7],
                exclusion_date=r[8],
                reinstatement_date=r[9],
                waiver_date=r[10],
            )
            people = []
        people.append(
            NppesPerson(
                npi=r[11],
                last_name=r[12],
                first_name=r[13],
                middle_name=r[14],
                practice_state=r[15],
                license_states=tuple(r[16] or ()),
                is_active=r[17],
            )
        )
    if current is not None:
        yield current, people


def _params(candidate: Candidate, evidence_id: Any, run_started: Any) -> dict[str, Any]:
    leie, person = candidate.leie, candidate.person
    return {
        "leie_key": leie.leie_key,
        "npi": person.npi,
        "leie_last_name": leie.last_name,
        "leie_first_name": leie.first_name,
        "leie_middle_name": leie.middle_name,
        "leie_state": leie.state,
        "leie_general_category": leie.general_category,
        "leie_specialty": leie.specialty,
        "exclusion_type": leie.exclusion_type,
        "exclusion_date": leie.exclusion_date,
        "reinstatement_date": leie.reinstatement_date,
        "waiver_date": leie.waiver_date,
        "nppes_last_name": person.last_name,
        "nppes_first_name": person.first_name,
        "nppes_middle_name": person.middle_name,
        "nppes_practice_state": person.practice_state,
        "nppes_is_active": person.is_active,
        "match_detail": json.dumps(candidate.detail, sort_keys=True),
        "match_confidence": candidate.confidence,
        "candidate_count": candidate.candidate_count,
        "leie_evidence_id": evidence_id,
        "run_started": run_started,
    }


def record_candidates(conn: Any, evidence_id: Any) -> MatchSummary:
    """Match the staged LEIE file against NPPES and write the candidates.

    Runs inside the oig_leie load transaction, after ``stg_oig_leie`` is staged
    with a ``leie_key`` column. Writes only ``leie_npi_candidates``.

    When ``nppes_providers`` holds no individuals, nothing is matched and
    nothing is superseded: an empty directory says nothing about last month's
    candidates.

    Args:
        conn: Open connection inside the load transaction.
        evidence_id: The LEIE file evidence row, cited by every candidate.

    Returns:
        Counts for the evidence row and the log.
    """
    summary = MatchSummary()
    with conn.cursor() as cur:
        cur.execute("select exists (select 1 from nppes_providers where entity_type = 1)")
        row = cur.fetchone()
        summary.nppes_rows_available = bool(row and row[0])
        if not summary.nppes_rows_available:
            return summary
        cur.execute("select now()")
        run_started = _scalar(cur)
        cur.execute(_CREATE_NAMED)
        cur.execute("select count(*) from stg_oig_leie_named")
        summary.rows_eligible = int(_scalar(cur))
        cur.execute("create index on stg_oig_leie_named (last_key)")
        cur.execute("analyze stg_oig_leie_named")

    pending: list[dict[str, Any]] = []

    def flush() -> None:
        if pending:
            with conn.cursor() as write:
                write.executemany(_UPSERT_CANDIDATE, pending)
            summary.candidates_written += len(pending)
            pending.clear()

    # A server-side cursor streams the pairs: a common surname in a large state
    # can block thousands of NPIs, and the whole pair set need not fit in memory.
    with conn.cursor(name="leie_npi_pairs") as pairs:
        pairs.itersize = _PAIR_BATCH
        pairs.execute(_SELECT_PAIRS)
        for leie, people in _iter_pairs(pairs):
            candidates, ambiguous = match_row(leie, people)
            if ambiguous:
                summary.rows_too_ambiguous += 1
                continue
            if candidates:
                summary.rows_with_candidates += 1
            for candidate in candidates:
                label = f"{candidate.first_name}/{candidate.middle_name}"
                summary.by_basis[label] = summary.by_basis.get(label, 0) + 1
                pending.append(_params(candidate, evidence_id, run_started))
            if len(pending) >= _PAIR_BATCH:
                flush()
    flush()

    with conn.cursor() as cur:
        cur.execute(_SUPERSEDE, {"run_started": run_started})
        summary.candidates_superseded = cur.rowcount
    return summary
