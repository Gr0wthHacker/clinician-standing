"""Monthly digest per roster, as HTML. It states which sources were and were not checked, so a
clean month says what was looked at, and it carries the NPI-only matching note."""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime

from ..api import service
from ..api.store import StandingStore

__all__ = ["NPI_ONLY_NOTE", "render_digest"]

NPI_ONLY_NOTE = (
    "Exclusion matching is by NPI only. Most OIG LEIE rows carry no NPI, so a clean result "
    "means no NPI match in the rows that carry one. It is not a credentialing decision."
)

_KIND_LABEL = {
    "exclusion_new": "New exclusion match",
    "exclusion_reinstated": "Reinstatement",
    "license_adverse": "License status change",
    "license_discipline": "Discipline reported",
    "license_expiring": "License expiring",
    "npi_missing": "NPI not in CMS file",
    "npi_returned": "NPI back in CMS file",
    "source_stale": "Source past freshness limit",
}


def render_digest(
    conn: sqlite3.Connection,
    store: StandingStore,
    roster_id: str,
    period_start: str,
    period_end: str,
    now: datetime,
) -> str:
    e = html.escape
    roster = conn.execute(
        "select org_name from monitor_rosters where roster_id = ?", (roster_id,)
    ).fetchone()
    if roster is None:
        raise KeyError(roster_id)
    members = conn.execute(
        "select count(*) from monitor_roster_members where roster_id = ? and removed_at is null",
        (roster_id,),
    ).fetchone()[0]
    alerts = conn.execute(
        "select * from monitor_alerts where roster_id = ? and created_at >= ? and created_at < ?"
        " order by delivery desc, kind, npi",
        (roster_id, period_start, period_end),
    ).fetchall()
    block = service.sources_response(store, now).sources
    rows = (
        "".join(
            f"<tr><td>{e(_KIND_LABEL.get(a['kind'], a['kind']))}</td><td>{e(a['npi'] or '')}</td>"
            f"<td>{e(json.loads(a['detail'])['message'])}</td><td>{e(a['source_key'] or '')}</td>"
            f"<td>{e((a['source_as_of'] or '')[:10])}</td><td>{e(a['status'])}</td></tr>"
            for a in alerts
        )
        or '<tr><td colspan="6">No changes this period in the sources checked below.</td></tr>'
    )
    checked = "".join(
        f"<li>{e(s.display_name or s.key)}: as of {e(s.as_of.date().isoformat() if s.as_of else 'unknown')}"
        f"{' (past freshness limit)' if s.stale else ''}</li>"
        for s in block.checked
    )
    not_checked = "".join(
        f"<li>{e(s.display_name or s.key)}: {e(s.reason_not_checked or 'not ingested')}</li>"
        for s in block.not_checked
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Clinician Standing Monitor digest</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1d2433}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #dde2ea;padding:.4rem;text-align:left;vertical-align:top}}
.note{{background:#f4f6f9;padding:.75rem;border-radius:6px}}</style></head><body>
<h1>Clinician Standing Monitor</h1>
<p>{e(roster["org_name"])} &middot; {e(period_start[:10])} to {e(period_end[:10])} &middot; {members} clinicians on the roster</p>
<h2>Changes</h2>
<table><thead><tr><th>Change</th><th>NPI</th><th>Detail</th><th>Source</th><th>As of</th><th>Status</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Sources checked</h2><ul>{checked}</ul>
<h2>Sources not checked</h2><ul>{not_checked}</ul>
<p class="note">{e(NPI_ONLY_NOTE)} {e(service.SCOPE)}</p>
</body></html>"""
