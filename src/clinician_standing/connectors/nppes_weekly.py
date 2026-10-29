"""NPPES weekly incremental file.

CMS publishes, beside the monthly full replicate, a weekly file holding only the
NPIs added, changed or deactivated that week, in the same column layout
(``NPPES_Data_Dissemination_<MMDDYY>_<MMDDYY>_Weekly_V2.zip``, data member
``npidata_pfile_<from>-<to>.csv``). Applying it narrows the freshness window of
``nppes_providers`` from a month to a week.

Everything about parsing is inherited from :class:`NppesConnector`. What
differs is the load, because a weekly file is a change set, not a snapshot:

* **Every row in the file is written.** The diff against last week's file is
  kept for reporting only; an NPI absent this week has not left the registry,
  it simply did not change.
* **Nothing is ever marked absent.** The full replicate owns ``absent_since``.
* **An older row never overwrites a newer one.** The upsert only takes a row
  whose ``Last Update Date`` is on or after the stored one, so a weekly file
  applied after a newer monthly replicate cannot roll a provider back. A
  deactivation stub carries no update date and always applies, keeping the
  stored name and taxonomy exactly as the monthly load does.

Only the newest weekly file on the downloads page is applied per run. A missed
week is covered by the next monthly replicate; it is not backfilled here.

LIVE DOWNLOAD IS UNTESTED. The file-name pattern follows the CMS naming above;
the downloads page was unreachable (maintenance) when this was written, so the
discovery regex and the member layout are verified only against fixtures in
that shape.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime
from typing import ClassVar

from ..db import copy_from_csv, transaction
from ..evidence import store_evidence_for_file
from .base import ConnectorError, DiffResult
from .nppes import _CREATE_STAGING, INDEX_URL, STAGING_COLUMNS, NppesConnector, _upsert_sql

__all__ = ["NppesWeeklyConnector", "find_weekly_link"]

#: ``..._<MMDDYY>_<MMDDYY>_Weekly[_V2].zip``; the two dates bound the week.
_WEEKLY_LINK = re.compile(
    r"""href\s*=\s*["']([^"']*NPPES_Data_Dissemination_(\d{6})_(\d{6})_Weekly(_V2)?\.zip)["']""",
    re.IGNORECASE,
)

# The monthly upsert plus one condition: never move a row backwards in time.
_WEEKLY_UPSERT = (
    _upsert_sql()
    + "\nwhere excluded.last_update_date is null"
    + "\n   or nppes_providers.last_update_date is null"
    + "\n   or excluded.last_update_date >= nppes_providers.last_update_date"
)


def _week_end(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%m%d%y").date()
    except ValueError:
        return None


def find_weekly_link(page: str, page_url: str = INDEX_URL) -> str | None:
    """Find the newest weekly incremental on the NPPES downloads page.

    The newest is the link with the latest week-end date. V.2 wins over V.1 for
    the same week. Relative links are resolved against ``page_url``.

    Args:
        page: HTML of the downloads page.
        page_url: The page's own URL, for resolving relative links.

    Returns:
        The absolute URL, or None when the page lists no weekly file.
    """
    best: tuple[date, bool, str] | None = None
    for href, _start, end, v2 in _WEEKLY_LINK.findall(page):
        week_end = _week_end(end)
        if week_end is None:
            continue
        rank = (week_end, bool(v2), href)
        if best is None or rank[:2] > best[:2]:
            best = rank
    return urllib.parse.urljoin(page_url, best[2]) if best else None


class NppesWeeklyConnector(NppesConnector):
    """Apply the newest NPPES weekly incremental to ``nppes_providers``."""

    key: ClassVar[str] = "nppes_weekly"
    display_name: ClassVar[str] = "NPPES NPI Registry Weekly Incremental"
    cadence: ClassVar[str] = "weekly"
    # 0018 seeds 14; ensure_registered() adopts the registry's value.
    freshness_sla_days: int = 14
    # A weekly file's size is the week's activity, not the registry's: a quiet
    # week is legitimately a fraction of a busy one. The floor would refuse it.
    min_rows_fraction: ClassVar[float] = 0.0

    def discover_download_url(self) -> str:
        """Read the newest weekly link off the NPPES downloads page.

        Raises:
            ConnectorError: When the page carries no weekly link.
        """
        page = self.fetch_text(INDEX_URL)
        url = find_weekly_link(page)
        if url is None:
            raise ConnectorError(
                f"no NPPES_Data_Dissemination_<MMDDYY>_<MMDDYY>_Weekly[_V2].zip link on "
                f"{INDEX_URL}; CMS may have renamed the file"
            )
        self.log.info("NPPES weekly incremental: %s", url)
        return self.require_allowed_url(url)

    def load(self, diff: DiffResult) -> None:
        """Write file evidence, then upsert every row of the weekly file.

        Args:
            diff: Change set against last week's file. Reported, not used to
                choose rows; see the module docstring.
        """
        if self.fetched_path is None or self.fetched_checksum is None:
            raise ConnectorError("load() called before fetch()")

        with transaction(None, self.settings) as conn:
            self.ensure_registered(conn)
            evidence_id = store_evidence_for_file(
                self.key,
                self.request_ref,
                self.fetched_path,
                parsed={
                    "member": self.member_name,
                    "incremental": True,
                    "rows_read": self.rows_read,
                    "rows_rejected_bad_npi": self.rows_rejected,
                    "deactivated_stubs": self.deactivated_stubs,
                    "taxonomy_slots": self.taxonomy_slots,
                    "lines_decoded_latin1": self.decode_stats.latin1_lines,
                    "missing_optional_fields": self.missing_optional_fields,
                    "rows_new_vs_last_week": diff.rows_new,
                    "rows_changed_vs_last_week": diff.rows_changed,
                },
                match_keys={"npi": "exact", "method": "bulk_file"},
                freshness_days=self.freshness_sla_days,
                conn=conn,
                fetched_at=self.fetched_at,
                settings=self.settings,
                sha256=self.fetched_checksum,
            )
            self.evidence_id = evidence_id

            with conn.cursor() as cur:
                cur.execute(_CREATE_STAGING)
            staged = copy_from_csv(
                conn,
                "stg_nppes",
                STAGING_COLUMNS,
                (tuple(row[c] for c in STAGING_COLUMNS) for row in self.parse(self.fetched_path)),
                batch_size=self.settings.copy_batch_size,
            )
            with conn.cursor() as cur:
                cur.execute("analyze stg_nppes")
                cur.execute(_WEEKLY_UPSERT, {"evidence_id": evidence_id})
                upserted = cur.rowcount
            self.log.info(
                "nppes_weekly staged=%s upserted=%s (rows older than the stored record skipped=%s)",
                f"{staged:,}",
                f"{upserted:,}",
                f"{max(staged - upserted, 0):,}",
            )
