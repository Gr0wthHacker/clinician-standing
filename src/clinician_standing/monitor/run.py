"""One monitor pass: read every rostered NPI once, diff, write alerts, send immediate ones."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..api.store import StandingStore
from .diff import Alert, diff_snapshots
from .notify import Message, Notifier, NullNotifier
from .snapshot import take_snapshot
from .store import active_npis, write_alert

__all__ = ["RunResult", "release_held", "run_monitor", "send_pending_immediate"]


@dataclass(frozen=True)
class RunResult:
    run_id: int
    npis_read: int
    alerts_written: int
    immediate_sent: int


def _source_as_of(resp_sources: dict[str, str | None], key: str | None) -> str | None:
    return resp_sources.get(key) if key else None


def run_monitor(
    conn: sqlite3.Connection,
    store: StandingStore,
    now: datetime,
    *,
    trigger: str = "manual",
    notifier: Notifier | None = None,
    expiry_window_days: int = 60,
) -> RunResult:
    now_s = now.isoformat()
    run_id = int(
        conn.execute(
            "insert into monitor_runs (started_at, trigger) values (?, ?)", (now_s, trigger)
        ).lastrowid
        or 0
    )
    rosters_by_npi = active_npis(conn)
    written = 0
    stale_seen: set[tuple[str, str]] = set()
    for npi, roster_ids in rosters_by_npi.items():
        snap, resp = take_snapshot(store, npi, now)
        row = conn.execute(
            "select hash, snapshot from monitor_snapshots where npi = ?", (npi,)
        ).fetchone()
        before = json.loads(row["snapshot"]) if row else None
        alerts = diff_snapshots(
            npi, before, snap.data, today=now.date(), expiry_window_days=expiry_window_days
        )
        as_of = {s.key: (s.as_of.isoformat() if s.as_of else None) for s in resp.sources.checked}
        for status in resp.sources.checked:
            if status.stale:
                for rid in roster_ids:
                    if (rid, status.key) not in stale_seen:
                        stale_seen.add((rid, status.key))
                        a = Alert(
                            None,
                            "source_stale",
                            "digest",
                            f"{status.display_name or status.key} is past its "
                            f"{status.freshness_sla_days}-day freshness limit "
                            f"(as of {as_of.get(status.key) or 'unknown'}).",
                            source_key=status.key,
                        )
                        written += write_alert(conn, rid, a, now_s, as_of.get(status.key))
        for a in alerts:
            for rid in roster_ids:
                written += write_alert(conn, rid, a, now_s, _source_as_of(as_of, a.source_key))
        conn.execute(
            "insert into monitor_snapshots (npi, taken_at, hash, snapshot) values (?, ?, ?, ?)"
            " on conflict (npi) do update set taken_at = excluded.taken_at, hash = excluded.hash,"
            " snapshot = excluded.snapshot",
            (npi, now_s, snap.hash, json.dumps(snap.data, sort_keys=True)),
        )
    sent = send_pending_immediate(conn, notifier or NullNotifier(), now)
    conn.execute(
        "update monitor_runs set finished_at = ?, npis_read = ?, alerts_written = ? where run_id = ?",
        (datetime.now(now.tzinfo).isoformat(), len(rosters_by_npi), written, run_id),
    )
    conn.commit()
    return RunResult(run_id, len(rosters_by_npi), written, sent)


def release_held(conn: sqlite3.Connection, alert_id: str, confirmed_by: str) -> bool:
    """A person confirmed a held exclusion alert against the source record; let it send."""
    cur = conn.execute(
        "update monitor_alerts set status = 'pending', acknowledged_by = ? where alert_id = ? and status = 'held'",
        (confirmed_by, alert_id),
    )
    conn.commit()
    return cur.rowcount == 1


def send_pending_immediate(conn: sqlite3.Connection, notifier: Notifier, now: datetime) -> int:
    rows = conn.execute(
        "select a.alert_id, a.npi, a.kind, a.detail, a.source_key, a.source_as_of, r.alert_email, r.org_name"
        " from monitor_alerts a join monitor_rosters r using (roster_id)"
        " where a.delivery = 'immediate' and a.status = 'pending' and r.alert_email is not null"
        " order by a.created_at, a.alert_id"
    ).fetchall()
    sent = 0
    for r in rows:
        detail = json.loads(r["detail"])
        body = (
            f"{detail['message']}\n\nNPI: {r['npi']}\nSource: {r['source_key'] or 'n/a'}"
            f" (as of {r['source_as_of'] or 'unknown'})\n\n"
            "This alert reports what the source contained as of that date. Exclusion matching is by "
            "NPI only. It is not a credentialing decision."
        )
        msg = Message(
            to=r["alert_email"],
            subject=f"Clinician Standing alert: {r['kind'].replace('_', ' ')}",
            body=body,
            ref=r["alert_id"],
        )
        if notifier.send(msg):
            conn.execute(
                "update monitor_alerts set status = 'sent', sent_at = ? where alert_id = ?",
                (now.isoformat(), r["alert_id"]),
            )
            sent += 1
    conn.commit()
    return sent
