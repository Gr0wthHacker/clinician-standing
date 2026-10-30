"""Stripe line for the Monitor. The price lives in Stripe, not in this repo: the price id comes
from ``STRIPE_PRICE_STANDING_MONITOR`` and the minimum billed quantity from
``STANDING_MONITOR_MIN_CLINICIANS``. It is a separate SKU from the PPPM subscription, so the PPPM
floor in :mod:`clinician_standing.pricing` does not apply (``is_pppm_floored = false``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["MonitorLine", "monitor_line"]


@dataclass(frozen=True)
class MonitorLine:
    price: str
    quantity: int
    active_clinicians: int
    is_pppm_floored: bool = False
    metadata: tuple[tuple[str, str], ...] = (
        ("venture", "clinician-standing"),
        ("group", "1"),
        ("sku", "standing-monitor"),
    )


def monitor_line(active_clinicians: int, env: dict[str, str] | None = None) -> MonitorLine:
    """The subscription item for a roster: quantity is active clinicians, raised to the minimum."""
    env = dict(os.environ) if env is None else env
    price = env.get("STRIPE_PRICE_STANDING_MONITOR", "").strip()
    if not price.startswith("price_"):
        raise RuntimeError("STRIPE_PRICE_STANDING_MONITOR is not set to a Stripe price id")
    minimum = int(env.get("STANDING_MONITOR_MIN_CLINICIANS", "1") or "1")
    return MonitorLine(
        price=price, quantity=max(active_clinicians, minimum), active_clinicians=active_clinicians
    )
