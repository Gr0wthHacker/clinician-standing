"""Refreshing stale sources -- the automatic half of SOURCE_STALE (PRD 8.3).

When the classifier raises ``SOURCE_STALE`` on an obligation, the PRD's resolver
is "automatic re-fetch, then QA if still stale." The re-fetch is a source-level
act, not a per-obligation one: a source whose latest successful run is older than
its ``freshness_sla_days`` makes *every* assertion derived from it stale, so the
fix is to re-ingest that source once. If the re-ingest still fails or the
publisher genuinely has nothing newer, the next classifier pass raises
``SOURCE_STALE`` again and it escalates to QA on its own -- no special path
needed.

This module finds the stale sources; the connector registry runs them. The
selection is a pure function so "which sources are stale" is testable without a
database or the network.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from .config import Settings
from .connectors import CONNECTORS, RunResult
from .db import connect, fetch_all

__all__ = ["refresh_stale", "select_stale_keys", "stale_source_keys"]

LOGGER = logging.getLogger(__name__)

_QUERY_SOURCE_FRESHNESS = """
select s.key, r.last_ok, s.freshness_sla_days, s.enabled
from sources s
left join lateral (
    select max(finished_at) as last_ok
    from source_runs
    where source_key = s.key and status = 'ok'
) r on true
where s.deleted_at is null
order by s.key
"""


def select_stale_keys(
    rows: Sequence[Sequence[Any]], connector_keys: Sequence[str], now: datetime
) -> list[str]:
    """Return the enabled, connectorized sources whose freshness has lapsed.

    A source is stale when it has never had a successful run, or its last one
    finished more than ``freshness_sla_days`` before ``now``. Only sources with
    a registered connector are returned -- a stale source no code can fetch (a
    disabled state board, say) is not something a re-fetch can fix, and belongs
    in QA, not here.

    Args:
        rows: ``(key, last_ok, freshness_sla_days, enabled)`` per source.
        connector_keys: Registry keys that have a runnable connector.
        now: The reference time.

    Returns:
        Stale source keys, in the order given.
    """
    known = set(connector_keys)
    stale: list[str] = []
    for key, last_ok, sla, enabled in rows:
        if not enabled or key not in known:
            continue
        if last_ok is None or last_ok < now - timedelta(days=int(sla)):
            stale.append(key)
    return stale


def stale_source_keys(
    conn: psycopg.Connection,
    *,
    connector_keys: Sequence[str] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Read the run log and return the stale, runnable source keys."""
    now = now or datetime.now(UTC)
    keys = connector_keys if connector_keys is not None else list(CONNECTORS)
    return select_stale_keys(fetch_all(conn, _QUERY_SOURCE_FRESHNESS), keys, now)


def refresh_stale(settings: Settings | None = None, *, dry_run: bool = False) -> list[RunResult]:
    """Re-ingest every stale source once. Returns each run's result.

    A dry run reports which sources would be refreshed and runs the connectors in
    their own dry-run mode (fetch, parse and diff, no load). One connector's
    failure does not stop the rest: ``Connector.run`` never raises.
    """
    with connect(settings) as conn:
        keys = stale_source_keys(conn)
    if not keys:
        LOGGER.info("no stale sources; nothing to refresh")
        return []
    LOGGER.info("refreshing %s stale source(s): %s", len(keys), ", ".join(keys))
    results: list[RunResult] = []
    for key in keys:
        results.append(CONNECTORS[key](settings).run(dry_run=dry_run))
    return results
