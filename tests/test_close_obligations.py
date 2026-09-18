"""Closing obligations the roster no longer implies (engine, roster-shrink).

Pure tests for :func:`~clinician_standing.engine.obligations_to_close`: which
open obligations an engine run soft-deletes when their duty is no longer planned.
The write itself is covered by the database-marked engine tests.
"""

from __future__ import annotations

from uuid import UUID

from conftest import require

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing import engine as eng
except ImportError:  # pragma: no cover
    eng = None  # type: ignore[assignment]

needs_engine = require("clinician_standing.engine", "obligations_to_close")

CL = UUID("cccccccc-0000-4000-8000-000000000001")
PR = UUID("aaaaaaaa-0000-4000-8000-000000000001")


def oid(n: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{n:012d}")


def key(otype: str, state: str = "", payer: str = "") -> tuple:
    return (CL, PR, otype, state, payer)


def row(n: int, otype: str, status: str, state: str = "", payer: str = "") -> tuple:
    # Shape of _QUERY_OPEN_OBLIGATION_IDS.
    return (oid(n), CL, PR, otype, state, payer, status)


@needs_engine
def test_unplanned_unstarted_rows_are_closed() -> None:
    planned = {key("license_renewal", "TX")}
    open_rows = [
        row(1, "license_renewal", "pending", "TX"),  # planned -> kept
        row(2, "csr_renewal", "pending", "TX"),  # not planned, pending -> closed
        row(3, "ce_cycle", "queued", "TX"),  # not planned, queued -> closed
    ]
    assert eng.obligations_to_close(planned, open_rows) == [oid(2), oid(3)]


@needs_engine
def test_in_progress_and_exception_are_left_for_a_human() -> None:
    planned: set = set()  # the whole roster vanished
    open_rows = [
        row(1, "license_renewal", "in_progress", "TX"),  # someone is on it
        row(2, "exclusion_screen", "exception"),  # a standing finding
        row(3, "license_renewal", "pending", "TX"),  # unstarted -> closed
    ]
    assert eng.obligations_to_close(planned, open_rows) == [oid(3)]


@needs_engine
def test_nothing_closed_when_everything_is_planned() -> None:
    planned = {key("license_renewal", "TX"), key("exclusion_screen")}
    open_rows = [
        row(1, "license_renewal", "pending", "TX"),
        row(2, "exclusion_screen", "queued"),
    ]
    assert eng.obligations_to_close(planned, open_rows) == []


@needs_engine
def test_state_is_compared_stripped() -> None:
    # A char(2) column can arrive padded; the key comparison strips it.
    planned = {key("license_renewal", "TX")}
    open_rows = [row(1, "license_renewal", "pending", "TX ")]
    assert eng.obligations_to_close(planned, open_rows) == []
