"""Pricing -- rules as code, with the $200 PPPM floor (BUILD_PLAN WP1.1, A2.3).

Pricing rules are code, not copy. The rack rate comes from ``price_book``, the
discount from ``discount_rules``, and this module computes the effective price
that a quote line stores and Stripe bills. The one rule that must never break:
a Clinician Standing subscription's effective per-clinician-per-month price may
never fall below **$200 = 20,000 cents**, whatever discount applies.

Everything is in integer cents. The rounding matches Postgres ``round(numeric)``
(half away from zero) so :func:`effective_unit_price_cents` and the SQL
``app.price_effective`` agree to the cent -- a database test pins that.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "FLOOR_PPPM_CENTS",
    "DiscountTier",
    "discount_percent_for",
    "effective_unit_price_cents",
]

#: The absolute Clinician Standing PPPM floor, in cents. $200.00.
FLOOR_PPPM_CENTS = 20000


def _as_decimal(value: object) -> Decimal:
    """Coerce a number to Decimal without inheriting binary-float error."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def effective_unit_price_cents(
    rack_price_cents: int,
    discount_percent: float | Decimal,
    *,
    is_pppm_floored: bool,
) -> int:
    """Return the effective unit price in cents.

    The discount is applied AFTER the rack rate (A2.3), rounded to the nearest
    cent half-away-from-zero to match Postgres, then floored at $200 for a
    Clinician Standing PPPM line.

    Args:
        rack_price_cents: The rack rate in cents.
        discount_percent: The discount, 0..100, applied after the rack rate.
        is_pppm_floored: True for a Clinician Standing PPPM subscription line,
            the only line the floor governs.

    Returns:
        The effective price in cents, never below :data:`FLOOR_PPPM_CENTS` when
        ``is_pppm_floored``.
    """
    factor = Decimal(1) - _as_decimal(discount_percent) / Decimal(100)
    net = int((Decimal(rack_price_cents) * factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return max(net, FLOOR_PPPM_CENTS) if is_pppm_floored else net


class DiscountTier:
    """One ``discount_rules`` row: a threshold and the percent at or above it."""

    __slots__ = ("min_threshold", "percent")

    def __init__(self, min_threshold: int, percent: float | Decimal) -> None:
        self.min_threshold = min_threshold
        self.percent = _as_decimal(percent)


def discount_percent_for(count: int, tiers: Iterable[DiscountTier]) -> Decimal:
    """Return the discount percent for ``count`` units, highest matching tier.

    A tier applies at or above its ``min_threshold``; the tier with the largest
    threshold that ``count`` reaches wins. No matching tier means no discount.

    Args:
        count: The unit count (e.g. billing clinicians).
        tiers: The discount schedule for the brand.

    Returns:
        The discount percent as a Decimal (0..100).
    """
    applicable = [t for t in tiers if t.min_threshold <= count]
    if not applicable:
        return Decimal(0)
    return max(applicable, key=lambda t: t.min_threshold).percent
