"""Pricing rules, with the $200 PPPM floor (BUILD_PLAN WP1.1, A2.3).

The pure tests prove the floor can never be breached and that the discount is
applied after the rack rate. The database-marked tests prove the SQL
``app.price_effective`` agrees with the Python function to the cent, that the
check constraint rejects a stored line under the floor, and that the seeded
Clinician Standing rack rates match A2.3.
"""

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

from clinician_standing.pricing import (
    FLOOR_PPPM_CENTS,
    DiscountTier,
    discount_percent_for,
    effective_unit_price_cents,
)

# Clinician Standing rack rates (A2.3), in cents.
CS_RACKS = (20000, 35000, 40000)
# The D5 default discount schedule.
D5_TIERS = [DiscountTier(0, 0), DiscountTier(10, 5), DiscountTier(25, 10)]


# --------------------------------------------------------------------------- #
# The floor -- the rule that must never break
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rack", CS_RACKS)
@pytest.mark.parametrize("discount", range(0, 101))
def test_floored_price_never_below_200(rack: int, discount: int) -> None:
    assert effective_unit_price_cents(rack, discount, is_pppm_floored=True) >= FLOOR_PPPM_CENTS


def test_essential_tier_is_floored_flat_at_200_under_any_discount() -> None:
    for discount in (0, 5, 10, 15, 50, 100):
        assert effective_unit_price_cents(20000, discount, is_pppm_floored=True) == 20000


def test_unfloored_line_is_not_floored() -> None:
    # A one-off or non-CS line is not subject to the floor.
    assert effective_unit_price_cents(10000, 50, is_pppm_floored=False) == 5000


# --------------------------------------------------------------------------- #
# Discount is applied after the rack rate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("rack", "discount", "expected"),
    [
        (35000, 0, 35000),
        (35000, 5, 33250),  # standard, 5% off
        (35000, 10, 31500),
        (35000, 15, 29750),
        (40000, 10, 36000),  # complete, 10% off
    ],
)
def test_discount_applied_after_rack(rack: int, discount: int, expected: int) -> None:
    assert effective_unit_price_cents(rack, discount, is_pppm_floored=True) == expected


def test_rounding_is_half_away_from_zero() -> None:
    # 12345 * 0.995 = 12283.275 -> 12283; 10001 * 0.995 = 9950.995 -> 9951.
    assert effective_unit_price_cents(12345, Decimal("0.5"), is_pppm_floored=False) == 12283
    assert effective_unit_price_cents(10001, Decimal("0.5"), is_pppm_floored=False) == 9951


# --------------------------------------------------------------------------- #
# Discount selection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, 0), (1, 0), (9, 0), (10, 5), (24, 5), (25, 10), (100, 10)],
)
def test_discount_percent_for_d5_schedule(count: int, expected: int) -> None:
    assert discount_percent_for(count, D5_TIERS) == Decimal(expected)


def test_no_tiers_means_no_discount() -> None:
    assert discount_percent_for(50, []) == Decimal(0)


# --------------------------------------------------------------------------- #
# Database: the SQL function, the constraint, the seed
# --------------------------------------------------------------------------- #


@pytest.mark.database
def test_sql_price_effective_matches_python(db_connection) -> None:
    with db_connection.cursor() as cur:
        for rack in CS_RACKS:
            for discount in (0, 5, 10, 15, 33, 50, 100):
                for floored in (True, False):
                    cur.execute("select app.price_effective(%s, %s, %s)", (rack, discount, floored))
                    sql_value = cur.fetchone()[0]
                    py_value = effective_unit_price_cents(rack, discount, is_pppm_floored=floored)
                    assert sql_value == py_value, (rack, discount, floored)


@pytest.mark.database
def test_check_constraint_rejects_a_line_under_the_floor(db_connection) -> None:
    with db_connection.cursor() as cur:
        cur.execute("insert into quotes (brand) values ('clinician_standing') returning id")
        quote_id = cur.fetchone()[0]
        with pytest.raises(psycopg.Error):
            cur.execute(
                """
                insert into quote_lines (quote_id, product_code, unit, rack_price_cents,
                                         effective_unit_price_cents, is_pppm_floored)
                values (%s, 'cs_essential', 'pppm', 20000, 19999, true)
                """,
                (quote_id,),
            )


@pytest.mark.database
def test_seeded_clinician_standing_rack_rates(db_connection) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            "select product_code, rack_price_cents from price_book "
            "where product_code in ('cs_essential', 'cs_standard', 'cs_complete') "
            "order by rack_price_cents"
        )
        assert cur.fetchall() == [
            ("cs_essential", 20000),
            ("cs_standard", 35000),
            ("cs_complete", 40000),
        ]
