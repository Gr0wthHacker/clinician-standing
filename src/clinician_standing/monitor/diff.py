"""Compare two snapshots of one NPI and name every change as an alert.

Delivery follows the spec: exclusion and adverse license changes go out immediately; expiry
windows, a missing NPI and stale sources go in the monthly digest. A first snapshot (no previous
one) only alerts on what is already adverse, so loading a roster reports open exclusions and
adverse licenses once and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

__all__ = ["ADVERSE_LICENSE_STATUSES", "Alert", "diff_snapshots"]

Delivery = Literal["immediate", "digest"]

#: License statuses that send an immediate email when a record moves into them.
ADVERSE_LICENSE_STATUSES = frozenset({"expired", "lapsed", "suspended", "revoked", "probation"})


@dataclass(frozen=True)
class Alert:
    npi: str | None
    kind: str
    delivery: Delivery
    message: str
    before: Any = None
    after: Any = None
    source_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe(self) -> str:
        return f"{self.npi}|{self.kind}|{self.message}"


def _lic_key(r: dict[str, Any]) -> tuple[str, str, str]:
    return (r["state"], r["license_type"], r["license_number"] or "")


def _exc_key(m: dict[str, Any]) -> tuple[str, str, str]:
    return (m["source"], m["action_type"] or "", m["action_date"] or "")


def _label(r: dict[str, Any]) -> str:
    num = f" {r['license_number']}" if r.get("license_number") else ""
    return f"{r['state']} {r['license_type']}{num}"


def diff_snapshots(
    npi: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    *,
    today: date,
    expiry_window_days: int = 60,
) -> list[Alert]:
    alerts: list[Alert] = []
    prev = before or {"found": None, "exclusions": [], "licenses": []}

    # Identity: the NPI left or came back to the CMS Doctors and Clinicians file.
    if prev["found"] is True and not after["found"]:
        alerts.append(
            Alert(
                npi,
                "npi_missing",
                "digest",
                "NPI is no longer in the CMS Doctors and Clinicians file.",
                source_key="cms_dac",
            )
        )
    elif prev["found"] is False and after["found"]:
        alerts.append(
            Alert(
                npi,
                "npi_returned",
                "digest",
                "NPI is back in the CMS Doctors and Clinicians file.",
                source_key="cms_dac",
            )
        )

    # Exclusions.
    old_exc = {_exc_key(m): m for m in prev["exclusions"]}
    for key, m in {_exc_key(m): m for m in after["exclusions"]}.items():
        was = old_exc.get(key)
        what = f"{m['source'].upper()} {m['action_type'] or 'exclusion'} dated {m['action_date'] or 'unknown'}"
        if m["open"] and (was is None or not was["open"]):
            alerts.append(
                Alert(
                    npi,
                    "exclusion_new",
                    "immediate",
                    f"Open exclusion match: {what}.",
                    before=was,
                    after=m,
                    source_key=m["source_key"],
                )
            )
        elif not m["open"] and was is not None and was["open"]:
            alerts.append(
                Alert(
                    npi,
                    "exclusion_reinstated",
                    "immediate",
                    f"Reinstatement recorded {m['reinstated_date']} for {what}.",
                    before=was,
                    after=m,
                    source_key=m["source_key"],
                )
            )

    # Licenses.
    old_lic = {_lic_key(r): r for r in prev["licenses"]}
    horizon = today + timedelta(days=expiry_window_days)
    for key, r in {_lic_key(r): r for r in after["licenses"]}.items():
        was = old_lic.get(key)
        if r["status"] in ADVERSE_LICENSE_STATUSES and (
            was is None or was["status"] != r["status"]
        ):
            prior = f" (was {was['status']})" if was else ""
            alerts.append(
                Alert(
                    npi,
                    "license_adverse",
                    "immediate",
                    f"License {_label(r)} is {r['status']}{prior}.",
                    before=was,
                    after=r,
                    source_key=r["source_key"],
                )
            )
        if r["discipline_reported"] and not (was and was["discipline_reported"]):
            alerts.append(
                Alert(
                    npi,
                    "license_discipline",
                    "immediate",
                    f"Discipline reported on license {_label(r)}.",
                    before=was,
                    after=r,
                    source_key=r["source_key"],
                )
            )
        if r["status"] == "active" and r["expires_on"]:
            exp = date.fromisoformat(r["expires_on"])
            if today <= exp <= horizon:
                alerts.append(
                    Alert(
                        npi,
                        "license_expiring",
                        "digest",
                        f"License {_label(r)} expires {r['expires_on']}.",
                        after=r,
                        source_key=r["source_key"],
                    )
                )
    return alerts
