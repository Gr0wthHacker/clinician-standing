"""Obligations engine phase 2 (T908) and filing write-back (T909). Synthetic jurisdictions
(ZZ, YY) and example.invalid sources only: no real rule is asserted by these fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clinician_standing.obligations_lite import (
    FilingError,
    close_filing,
    connect,
    generate,
    load_roster_csv,
    load_rules_csv,
    open_filing,
    quote,
    roster_audit,
)
from clinician_standing.obligations_lite.__main__ import main
from clinician_standing.obligations_lite.generator import alert_dates, obligation_id
from clinician_standing.obligations_lite.report import render_audit

FIX = Path(__file__).parent / "fixtures" / "obligations_lite"
AS_OF = "2026-11-01"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = connect(":memory:")
    load_rules_csv(c, FIX / "rules.csv")
    load_roster_csv(
        c,
        FIX / "roster.csv",
        org_id="g1",
        org_name="Example Group",
        start_date="2026-10-01",
        default_owner="Ops lead",
    )
    return c


def rows(c: sqlite3.Connection) -> list[tuple]:
    return c.execute(
        "select obligation_id, clinician_id, rule_key, trigger, due_date, status, price_cents,"
        " government_fee_cents, rule_version from obligations order by obligation_id"
    ).fetchall()


def test_generator_turns_rules_and_roster_into_dated_priced_obligations(
    conn: sqlite3.Connection,
) -> None:
    r = generate(conn, AS_OF)
    by = {(x[1], x[2]): x for x in rows(conn)}
    renew = by[("9900000001", "ZZ:NP:license:renewal")]
    assert renew[4] == "2026-11-16"  # board expiry 2027-01-15 minus 60 lead days
    assert renew[6:8] == (15000, 10000)
    assert by[("9900000001", "YY:NP:license:initial")][4] == AS_OF  # missing state
    assert by[("9900000001", "YY:NP:license:initial")][7] is None  # fee not published stays null
    assert (
        by[("9900000002", "ZZ:NP:license:renewal")][5] == "needs_board_read"
    )  # expiry never computed
    assert by[("9900000002", "ZZ:NP:license:renewal")][4] is None
    assert by[("9900000004", "ZZ:NP:license:initial")][3] == "initial"
    assert ("9900000003", "ZZ:MD:license:renewal") in by
    assert ("9900000001", "YY:NP:license:renewal") not in by  # no license there yet, so no renewal
    assert r.by_trigger == {"renewal": 3, "initial": 2}
    types = {t for (t,) in conn.execute("select type from events")}
    assert types == {"new_state", "expiry_window"}


def test_reruns_are_idempotent(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    first = rows(conn)
    events = conn.execute("select count(*) from events").fetchone()[0]
    generate(conn, AS_OF, generated_at="2026-11-02")
    assert rows(conn) == first
    assert conn.execute("select count(*) from events").fetchone()[0] == events
    assert obligation_id("g1", "9900000001", "ZZ:NP:license:renewal") in {x[0] for x in first}


def test_rule_change_propagates_and_roster_shrink_removes_unfiled(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    conn.execute(
        "insert into rules select rule_key, 2, jurisdiction, profession, credential_type, trigger, 30,"
        " 17500, government_fee_cents, cycle_months, prerequisites, form, delegation_mechanism, source_url,"
        " '2026-11-01', verified_by, second_verifier, effective_date, 'fee change' from rules"
        " where rule_key = 'ZZ:NP:license:renewal'"
    )
    conn.execute("delete from roster_memberships where clinician_id = '9900000004'")
    r = generate(conn, AS_OF)
    by = {(x[1], x[2]): x for x in rows(conn)}
    assert by[("9900000001", "ZZ:NP:license:renewal")][8] == 2
    assert by[("9900000001", "ZZ:NP:license:renewal")][6] == 17500
    assert by[("9900000001", "ZZ:NP:license:renewal")][4] == "2026-12-16"
    assert ("9900000004", "ZZ:NP:license:initial") not in by
    assert r.removed == 1


def test_free_roster_audit_and_quote(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    a = roster_audit(conn, "g1", AS_OF)
    assert a.clinicians == 4
    assert {(x.clinician, x.jurisdiction) for x in a.missing_states} == {
        ("Placeholder One", "YY"),
        ("Placeholder Four", "ZZ"),
    }
    assert [x.clinician for x in a.upcoming] == ["Placeholder One"]
    assert [x.clinician for x in a.needs_board_read] == ["Placeholder Two"]
    assert a.gap_service_cents == 60000 + 60000 + 15000
    assert a.gap_government_cents == 25000 + 10000
    assert a.unpublished_fees == 1
    text = render_audit(a)
    assert "not published" in text and "https://example.invalid/zz/np-renewal" in text
    assert "—" not in text
    q = quote(conn, "g1", AS_OF, rack_pppm_cents=15000)
    assert q["subscription"]["effective_pppm_cents"] == 20000  # $200 floor holds
    assert q["subscription"]["monthly_cents"] == 80000
    assert len(q["filings"]) == 3


def test_filing_write_back_is_required_to_close(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    oid = obligation_id("g1", "9900000001", "ZZ:NP:license:renewal")
    fid = open_filing(conn, oid, "2026-11-10")
    with pytest.raises(FilingError, match="actual_processing_days, actual_fee_paid"):
        close_filing(
            conn,
            fid,
            approved_at="2026-12-01",
            actual_processing_days=None,
            actual_fee_paid_cents=None,
            rule_was_correct=True,
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("update filings set closed_at = '2026-12-01' where filing_id = ?", (fid,))
    close_filing(
        conn,
        fid,
        approved_at="2026-12-01",
        actual_processing_days=21,
        actual_fee_paid_cents=10000,
        rule_was_correct=True,
    )
    assert (
        conn.execute("select status from obligations where obligation_id = ?", (oid,)).fetchone()[0]
        == "closed"
    )
    with pytest.raises(FilingError, match="already closed"):
        close_filing(
            conn,
            fid,
            approved_at="2026-12-02",
            actual_processing_days=1,
            actual_fee_paid_cents=1,
            rule_was_correct=True,
        )
    generate(conn, "2026-12-05")
    assert (
        conn.execute("select status from obligations where obligation_id = ?", (oid,)).fetchone()[0]
        == "closed"
    )


def test_wrong_rule_opens_a_review_ticket(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    oid = obligation_id("g1", "9900000004", "ZZ:NP:license:initial")
    fid = open_filing(conn, oid, "2026-11-03")
    with pytest.raises(FilingError, match="blocker_encountered"):
        close_filing(
            conn,
            fid,
            approved_at="2027-01-10",
            actual_processing_days=68,
            actual_fee_paid_cents=27500,
            rule_was_correct=False,
        )
    close_filing(
        conn,
        fid,
        approved_at="2027-01-10",
        actual_processing_days=68,
        actual_fee_paid_cents=27500,
        rule_was_correct=False,
        blocker_encountered="Board added a fingerprint fee",
        rework_count=1,
    )
    t = conn.execute("select rule_key, rule_version, note from rule_review_tickets").fetchall()
    assert t == [("ZZ:NP:license:initial", 1, "Board added a fingerprint fee")]


def test_needs_board_read_cannot_be_filed(conn: sqlite3.Connection) -> None:
    generate(conn, AS_OF)
    with pytest.raises(FilingError, match="board"):
        open_filing(conn, obligation_id("g1", "9900000002", "ZZ:NP:license:renewal"), "2026-11-03")


def test_alert_dates() -> None:
    assert alert_dates("2027-01-15") == ["2026-09-17", "2026-11-16", "2026-12-16", "2027-01-08"]
    assert alert_dates(None) == []


def test_cli_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "o.sqlite")
    assert main(["load-rules", str(FIX / "rules.csv"), "--db", db]) == 0
    assert (
        main(
            [
                "load-roster",
                str(FIX / "roster.csv"),
                "--db",
                db,
                "--org",
                "g1",
                "--org-name",
                "Example Group",
                "--start",
                "2026-10-01",
            ]
        )
        == 0
    )
    assert main(["generate", "--db", db, "--as-of", AS_OF]) == 0
    assert main(["audit", "--db", db, "--org", "g1", "--as-of", AS_OF]) == 0
    out = capsys.readouterr().out
    assert "Roster audit: Example Group" in out
    oid = obligation_id("g1", "9900000001", "ZZ:NP:license:renewal")
    assert main(["file", oid, "--db", db, "--submitted", "2026-11-10"]) == 0
    assert main(["close", "1", "--db", db, "--approved", "2026-12-01"]) == 1
    assert (
        main(
            [
                "close",
                "1",
                "--db",
                db,
                "--approved",
                "2026-12-01",
                "--days",
                "21",
                "--fee",
                "10000",
                "--rule-correct",
                "yes",
            ]
        )
        == 0
    )
