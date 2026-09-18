"""Selecting stale sources to re-fetch (SOURCE_STALE, PRD 8.3).

Pure tests for :func:`~clinician_standing.refresh.select_stale_keys`: which
sources a refresh re-ingests. Running the connectors is covered by the
database-marked and connector tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import require

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing import refresh as rf
except ImportError:  # pragma: no cover
    rf = None  # type: ignore[assignment]

needs_refresh = require("clinician_standing.refresh", "select_stale_keys")

NOW = datetime(2026, 9, 18, tzinfo=UTC)
CONNECTORS = ["cms_dac", "oig_leie", "nursys"]


def row(key: str, last_ok: datetime | None, sla: int = 45, enabled: bool = True) -> tuple:
    return (key, last_ok, sla, enabled)


@needs_refresh
def test_never_run_source_is_stale() -> None:
    rows = [row("oig_leie", None)]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == ["oig_leie"]


@needs_refresh
def test_recent_run_is_fresh() -> None:
    rows = [row("oig_leie", NOW - timedelta(days=10), sla=45)]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == []


@needs_refresh
def test_run_older_than_sla_is_stale() -> None:
    rows = [row("oig_leie", NOW - timedelta(days=46), sla=45)]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == ["oig_leie"]


@needs_refresh
def test_disabled_source_is_never_refreshed() -> None:
    rows = [row("oig_leie", None, enabled=False)]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == []


@needs_refresh
def test_source_without_a_connector_is_skipped() -> None:
    # A stale state board with no runnable connector belongs in QA, not a refetch.
    rows = [row("state_ca", None)]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == []


@needs_refresh
def test_order_is_preserved_and_mixed_rows_filtered() -> None:
    rows = [
        row("cms_dac", NOW - timedelta(days=100)),  # stale
        row("oig_leie", NOW - timedelta(days=1)),  # fresh
        row("nursys", None),  # stale (never run)
        row("state_tx", None),  # no connector
    ]
    assert rf.select_stale_keys(rows, CONNECTORS, NOW) == ["cms_dac", "nursys"]
