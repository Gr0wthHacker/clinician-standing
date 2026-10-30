"""One NPI's standing reduced to the fields the monitor diffs.

The snapshot comes from the same ``service.check`` the API answers with. Fields that change on
every run without meaning anything (``checked_at``, ``last_confirmed_at``) are left out of the
hash so an unchanged record never produces an alert.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..api import service
from ..api.models import CheckRequest, StandingResponse
from ..api.store import StandingStore

__all__ = ["Snapshot", "snapshot_from_response", "take_snapshot"]


@dataclass(frozen=True)
class Snapshot:
    npi: str
    taken_at: str
    data: dict[str, Any]

    @property
    def hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _iso(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def snapshot_from_response(npi: str, resp: StandingResponse) -> dict[str, Any]:
    data: dict[str, Any] = {
        "found": resp.result == "found",
        "exclusions": [],
        "exclusion_status": None,
        "license_coverage": None,
        "licenses": [],
        "sources_checked": sorted(s.key for s in resp.sources.checked),
        "sources_stale": sorted(s.key for s in resp.sources.checked if s.stale),
    }
    if resp.clinicians:
        c = resp.clinicians[0]
        data["exclusion_status"] = c.exclusions.status
        data["exclusions"] = sorted(
            (
                {
                    "source": m.source,
                    "source_key": m.source_key,
                    "action_type": m.action_type,
                    "action_date": _iso(m.action_date),
                    "reinstated_date": _iso(m.reinstated_date),
                    "open": m.open,
                }
                for m in c.exclusions.matches
            ),
            key=lambda m: (m["source"], m["action_date"] or "", m["action_type"] or ""),
        )
        data["license_coverage"] = c.licenses.coverage
        data["licenses"] = sorted(
            (
                {
                    "state": r.state,
                    "license_type": r.license_type,
                    "license_number": r.license_number,
                    "status": r.status,
                    "expires_on": _iso(r.expires_on),
                    "discipline_reported": r.discipline_reported,
                    "source_key": r.source_key,
                }
                for r in c.licenses.records
            ),
            key=lambda r: (r["state"], r["license_type"], r["license_number"] or ""),
        )
    return data


def take_snapshot(
    store: StandingStore, npi: str, now: datetime
) -> tuple[Snapshot, StandingResponse]:
    """Read standing for one NPI through the API service and reduce it."""
    resp = service.check(store, CheckRequest(npi=npi), now=now)
    return Snapshot(npi=npi, taken_at=now.isoformat(), data=snapshot_from_response(npi, resp)), resp
