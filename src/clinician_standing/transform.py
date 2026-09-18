"""Row-shaping helpers shared by connectors.

The one rule that matters here is the CMS Doctors and Clinicians dedupe key.
That file carries one row per clinician *per practice location*: a physician at
three sites of the same group appears three times with the same
``(NPI, org_pac_id)`` and three different addresses. Collapse on that pair
before counting or loading, or the roster and every number derived from it are
inflated. On the September 2026 file, 3,388,628 lines collapse to 2,015,850
pairs -- 40.5% of the lines are duplicates of a pair already seen.

Deduping on NPI alone is also wrong: it merges a clinician's two groups into
one and loses an affiliation. Deduping on ``org_pac_id`` alone collapses a whole
group into a single clinician. The key is the pair.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
from typing import Any

__all__ = ["DAC_DEDUPE_KEY", "dedupe", "dedupe_iter", "row_key"]

#: The identity of a CMS Doctors and Clinicians row, in that file's own column
#: names. Address, city, ZIP, phone and the telehealth flag vary inside a single
#: pair and are deliberately not part of it.
DAC_DEDUPE_KEY: tuple[str, ...] = ("NPI", "org_pac_id")


def row_key(row: Mapping[str, Any], key: Sequence[str] = DAC_DEDUPE_KEY) -> tuple[Hashable, ...]:
    """Return the identity tuple of ``row`` under ``key``.

    Args:
        row: A source row.
        key: Column names forming the identity.

    Returns:
        A hashable tuple of the row's key values, missing columns as None.
    """
    return tuple(row.get(column) for column in key)


def dedupe_iter(
    rows: Iterable[Mapping[str, Any]], key: Sequence[str] = DAC_DEDUPE_KEY
) -> Iterator[Mapping[str, Any]]:
    """Yield the first row for each distinct ``key``, streaming.

    First-wins rather than last-wins so the output order matches the input for
    the rows that survive, which keeps diffs between two runs stable.

    Args:
        rows: Source rows.
        key: Columns forming the identity.

    Yields:
        One row per distinct key.
    """
    seen: set[tuple[Hashable, ...]] = set()
    for row in rows:
        identity = row_key(row, key)
        if identity in seen:
            continue
        seen.add(identity)
        yield row


def dedupe(
    rows: Iterable[Mapping[str, Any]], key: Sequence[str] = DAC_DEDUPE_KEY
) -> list[Mapping[str, Any]]:
    """Collapse ``rows`` to one per distinct ``key``.

    Idempotent: deduping an already-deduped list returns it unchanged.

    Args:
        rows: Source rows.
        key: Columns forming the identity. Defaults to :data:`DAC_DEDUPE_KEY`.

    Returns:
        The surviving rows, in input order.
    """
    return list(dedupe_iter(rows, key))
