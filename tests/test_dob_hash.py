"""Salted date-of-birth hashing (OIG LEIE).

A date of birth is a small input space, so an unsalted sha256 is reversible.
These pin the salt behaviour: it changes the digest, it is deterministic, and an
empty salt reproduces the old unsalted digest for backward-compatible change
detection.
"""

from __future__ import annotations

import hashlib
from datetime import date

from conftest import require

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing.connectors.oig_leie import dob_hash
except ImportError:  # pragma: no cover
    dob_hash = None  # type: ignore[assignment]

needs_leie = require("clinician_standing.connectors.oig_leie", "dob_hash")

DOB = date(1965, 3, 14)


@needs_leie
def test_none_hashes_to_none() -> None:
    assert dob_hash(None) is None
    assert dob_hash(None, "salt") is None


@needs_leie
def test_empty_salt_reproduces_the_unsalted_digest() -> None:
    # Backward compatible: with no salt, the change-detection key is unchanged.
    expected = hashlib.sha256(DOB.isoformat().encode("utf-8")).hexdigest()
    assert dob_hash(DOB) == expected
    assert dob_hash(DOB, "") == expected


@needs_leie
def test_salt_changes_the_digest() -> None:
    assert dob_hash(DOB, "pepper") != dob_hash(DOB)
    assert dob_hash(DOB, "pepper") != dob_hash(DOB, "other")


@needs_leie
def test_salted_digest_is_deterministic_and_hex() -> None:
    first = dob_hash(DOB, "pepper")
    assert first == dob_hash(DOB, "pepper")
    assert first is not None and len(first) == 64 and all(c in "0123456789abcdef" for c in first)
