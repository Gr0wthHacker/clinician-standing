"""Guards the (NPI, org_pac_id) dedupe requirement.

The CMS Doctors and Clinicians National Downloadable File carries one row per
clinician PER PRACTICE LOCATION. A clinician at three sites of the same group
is three rows. Counting the file raw overstates the roster and double-loads
affiliations, so every consumer must collapse on (NPI, org_pac_id) first.

Address, city, ZIP, phone and the telehealth flag all vary inside a single
pair and must not be part of the key.
"""

from __future__ import annotations

from clinician_standing.transform import DAC_DEDUPE_KEY, dedupe
from conftest import DAC_EXPECTED_PAIRS

DEDUPE_KEY = ("NPI", "org_pac_id")


def _pairs(rows):
    return {(row["NPI"], row["org_pac_id"]) for row in rows}


# --------------------------------------------------------------------------
# Fixture integrity. If these fail the fixture stopped exercising the bug.
# --------------------------------------------------------------------------
def test_fixture_contains_duplicate_location_rows(dac_rows, expected_pairs):
    assert len(dac_rows) == 6
    assert _pairs(dac_rows) == expected_pairs
    assert len(dac_rows) > len(expected_pairs), "fixture has no duplicates to collapse"


def test_fixture_duplicates_differ_only_outside_the_key(dac_rows):
    """The duplicate rows are genuinely different rows, not copies."""
    same_pair = [
        row for row in dac_rows if (row["NPI"], row["org_pac_id"]) == ("1234567893", "0042000001")
    ]
    assert len(same_pair) == 3
    assert len({row["adr_ln_1"] for row in same_pair}) == 3
    assert len({row["Provider Last Name"] for row in same_pair}) == 1


def test_naive_row_count_overstates_the_roster(dac_rows, expected_pairs):
    """6 rows, 3 real clinician-practice pairs: a 2x overstatement."""
    assert len(dac_rows) == 2 * len(expected_pairs)


def test_deduping_on_npi_alone_is_wrong(dac_rows):
    """NPI alone collapses a clinician's two groups into one, losing an affiliation."""
    by_npi = {row["NPI"] for row in dac_rows}
    assert len(by_npi) == 2
    assert len(by_npi) < len(DAC_EXPECTED_PAIRS), (
        "NPI-only dedupe must lose rows that (NPI, org_pac_id) keeps"
    )


def test_deduping_on_org_pac_id_alone_is_wrong(dac_rows):
    """Group alone collapses every clinician in the group into one row."""
    by_org = {row["org_pac_id"] for row in dac_rows}
    assert len(by_org) == 2
    assert len(by_org) < len(DAC_EXPECTED_PAIRS)


# --------------------------------------------------------------------------
# The package's dedupe. Imported directly: a rename or a broken import fails
# the suite, it does not skip it.
# --------------------------------------------------------------------------
def test_dedupe_key_is_the_pair():
    """The declared key is the pair, not NPI alone and not the group alone."""
    assert tuple(DAC_DEDUPE_KEY) == DEDUPE_KEY


def test_dedupe_collapses_duplicate_location_rows(dac_rows, expected_pairs):
    result = dedupe(dac_rows)

    assert len(result) == len(expected_pairs), (
        f"expected {len(expected_pairs)} rows after dedupe, got {len(result)}"
    )
    assert _pairs(result) == expected_pairs


def test_dedupe_is_idempotent(dac_rows):
    once = dedupe(dac_rows)
    twice = dedupe(once)
    assert _pairs(once) == _pairs(twice)
    assert len(once) == len(twice)


def test_dedupe_of_already_unique_rows_is_a_no_op(dac_rows):
    unique = dedupe(dac_rows)
    assert _pairs(dedupe(unique)) == _pairs(unique)


def test_dedupe_handles_empty_input():
    assert dedupe([]) == []


def test_dedupe_is_first_wins_and_order_preserving(dac_rows):
    """First-wins keeps the output order stable, which keeps run-to-run diffs stable."""
    result = dedupe(dac_rows)
    assert [row["adr_ln_1"] for row in result] == [
        "100 MAIN ST",  # first row of pair (1234567893, 0042000001)
        "500 GROUP WAY",  # first row of pair (1234567893, 0042000002)
        "100 MAIN ST",  # first row of pair (1987654320, 0042000001)
    ]
