"""Clinician Standing Monitor (T620) over synthetic in-memory standing data."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clinician_standing.api.store import MemoryStore
from clinician_standing.monitor import diff_snapshots, run_monitor
from clinician_standing.monitor.billing import monitor_line
from clinician_standing.monitor.digest import NPI_ONLY_NOTE, render_digest
from clinician_standing.monitor.notify import OutboxNotifier, notifier_from_env
from clinician_standing.monitor.run import release_held
from clinician_standing.monitor.store import add_roster, connect, load_members_csv

FIXTURE = Path(__file__).parent / "fixtures" / "api" / "standing_synthetic.json"
T1 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
ALPHA, BRAVO, CHARLIE, DELTA = "1990001012", "1990001020", "1990001038", "1990001046"


def _data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _clin(data: dict, npi: str) -> dict:
    return next(c for c in data["clinicians"] if c["npi"] == npi)


@pytest.fixture
def conn(tmp_path: Path):
    c = connect()
    add_roster(c, "r1", "Sample Group", T1.isoformat(), alert_email="ops@example.test")
    csv = tmp_path / "roster.csv"
    csv.write_text(
        f"npi,name,state,credential\n{ALPHA},A,MN,MD\n{CHARLIE},C,WI,NP\n{DELTA},D,MN,MD\n"
    )
    load_members_csv(c, "r1", csv, T1.isoformat())
    return c


def _alerts(conn) -> list[tuple[str, str, str]]:
    return sorted(
        (r["npi"] or "", r["kind"], r["status"])
        for r in conn.execute("select * from monitor_alerts")
    )


def test_first_run_then_no_change_writes_nothing_new(conn) -> None:
    store = MemoryStore.from_dict(_data())
    first = run_monitor(conn, store, T1)
    assert first.npis_read == 3
    again = run_monitor(conn, store, T1)
    assert again.alerts_written == 0


def test_new_exclusion_is_held_and_license_change_is_immediate(conn, tmp_path: Path) -> None:
    data = _data()
    run_monitor(conn, MemoryStore.from_dict(data), T1)
    before = set(_alerts(conn))
    v2 = copy.deepcopy(data)
    _clin(v2, ALPHA)["sanctions"] = copy.deepcopy(_clin(data, BRAVO)["sanctions"])
    _clin(v2, CHARLIE)["licenses"][0]["status"] = "suspended"
    _clin(v2, CHARLIE)["licenses"][0]["discipline_reported"] = True
    outbox = tmp_path / "outbox"
    res = run_monitor(conn, MemoryStore.from_dict(v2), T2, notifier=OutboxNotifier(outbox))
    new = set(_alerts(conn)) - before
    kinds = {(n, k) for n, k, _ in new}
    assert (ALPHA, "exclusion_new") in kinds
    assert (CHARLIE, "license_adverse") in kinds
    assert (CHARLIE, "license_discipline") in kinds
    held = [s for n, k, s in new if k == "exclusion_new"]
    assert held == ["held"]
    assert res.immediate_sent == 2  # license changes go now; the exclusion waits for review
    aid = conn.execute(
        "select alert_id from monitor_alerts where kind = 'exclusion_new'"
    ).fetchone()[0]
    assert release_held(conn, aid, "jack")
    from clinician_standing.monitor.run import send_pending_immediate

    assert send_pending_immediate(conn, OutboxNotifier(outbox), T2) == 1
    body = (outbox / f"{aid}.txt").read_text()
    assert "NPI only" in body and "not a credentialing decision" in body


def test_npi_missing_and_expiry_go_to_digest(conn) -> None:
    data = _data()
    run_monitor(conn, MemoryStore.from_dict(data), T1)
    v2 = copy.deepcopy(data)
    v2["clinicians"] = [c for c in v2["clinicians"] if c["npi"] != DELTA]
    _clin(v2, CHARLIE)["licenses"][0]["expiry_date"] = "2026-12-15"
    run_monitor(conn, MemoryStore.from_dict(v2), T2)
    rows = {
        (r["npi"], r["kind"]): r["delivery"] for r in conn.execute("select * from monitor_alerts")
    }
    assert rows[(DELTA, "npi_missing")] == "digest"
    assert rows[(CHARLIE, "license_expiring")] == "digest"


def test_digest_lists_sources_and_note(conn) -> None:
    store = MemoryStore.from_dict(_data())
    run_monitor(conn, store, T1)
    page = render_digest(conn, store, "r1", "2026-10-01", "2026-12-01", T1)
    assert "Sources checked" in page and "Sources not checked" in page
    assert NPI_ONLY_NOTE.split(".")[0] in page


def test_roster_refuses_extra_columns(tmp_path: Path) -> None:
    c = connect()
    add_roster(c, "r2", "X", T1.isoformat())
    bad = tmp_path / "bad.csv"
    bad.write_text(f"npi,name,dob\n{ALPHA},A,1980-01-01\n")
    with pytest.raises(ValueError, match="does not accept"):
        load_members_csv(c, "r2", bad, T1.isoformat())


def test_reinstatement_alert() -> None:
    m = {
        "source": "leie",
        "source_key": "oig_leie",
        "action_type": "1128a1",
        "action_date": "2019-06-01",
        "reinstated_date": None,
        "open": True,
    }
    before = {"found": True, "exclusions": [m], "licenses": []}
    after = {
        "found": True,
        "exclusions": [dict(m, open=False, reinstated_date="2026-11-01")],
        "licenses": [],
    }
    alerts = diff_snapshots(BRAVO, before, after, today=T2.date())
    assert [a.kind for a in alerts] == ["exclusion_reinstated"]


def test_billing_line_reads_price_from_env() -> None:
    with pytest.raises(RuntimeError):
        monitor_line(5, env={})
    line = monitor_line(
        5, env={"STRIPE_PRICE_STANDING_MONITOR": "price_x", "STANDING_MONITOR_MIN_CLINICIANS": "20"}
    )
    assert (line.quantity, line.is_pppm_floored) == (20, False)
    assert monitor_line(31, env={"STRIPE_PRICE_STANDING_MONITOR": "price_x"}).quantity == 31


def test_notifier_defaults_to_none() -> None:
    assert notifier_from_env({}).send.__self__.__class__.__name__ == "NullNotifier"  # type: ignore[attr-defined]
