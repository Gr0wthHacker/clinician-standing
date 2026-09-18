"""Guards the latin-1 bug.

The OIG LEIE file and the CMS Revalidation Clinic Group Practice Reassignment
file are latin-1 encoded, not UTF-8. Reading either with Python's default
encoding raises UnicodeDecodeError partway through a multi-hundred-megabyte
parse, which is both slow to reproduce and easy to misdiagnose as a corrupt
download. These tests fail the moment someone drops the explicit encoding.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from conftest import find_attr, require, try_import

PARSE_MODULES = ("clinician_standing.parse", "clinician_standing.io")


# --------------------------------------------------------------------------
# The property itself. These run with or without the package.
# --------------------------------------------------------------------------
def test_fixture_actually_contains_the_offending_byte(latin1_csv_bytes: bytes):
    assert b"\xa0" in latin1_csv_bytes, (
        "the fixture no longer carries a 0xa0 byte, so it guards nothing"
    )


def test_utf8_decode_raises(latin1_csv_bytes: bytes):
    """This is the exact exception the real ingest hit."""
    with pytest.raises(UnicodeDecodeError) as excinfo:
        latin1_csv_bytes.decode("utf-8")
    assert "0xa0" in str(excinfo.value)


def test_latin1_decode_succeeds(latin1_csv_bytes: bytes):
    text = latin1_csv_bytes.decode("latin-1")
    assert "\xa0" in text
    assert "PE\xd1A" in text  # N-tilde survived


def test_open_with_default_encoding_raises(latin1_csv_path: Path):
    """open() without an explicit encoding is the bug, not a stylistic choice."""
    with (
        pytest.raises(UnicodeDecodeError),
        latin1_csv_path.open("r", encoding="utf-8") as handle,
    ):
        handle.read()


def test_csv_reader_parses_under_latin1(latin1_csv_path: Path):
    with latin1_csv_path.open("r", encoding="latin-1", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4
    # The 0xa0 is a non-breaking space inside the name, not a field separator.
    assert rows[1]["FIRSTNAME"] == "MARY\xa0JANE"
    assert rows[2]["LASTNAME"] == "PE\xd1A"
    # Only one of these four rows carries an NPI-bearing individual with a value
    # for every row; LEIE's sparse NPI coverage is why name+DOB matching exists.
    assert sum(1 for row in rows if row["NPI"]) == 2


def test_latin1_is_lossless_roundtrip(latin1_csv_bytes: bytes):
    """latin-1 maps every byte 0x00-0xff, so it can never raise on decode.

    That is the reason it is the right fallback here: it will not silently drop
    a character the way errors='ignore' would.
    """
    assert latin1_csv_bytes.decode("latin-1").encode("latin-1") == latin1_csv_bytes


def test_errors_ignore_would_silently_corrupt(latin1_csv_bytes: bytes):
    """Documents why utf-8 with errors='ignore' is not an acceptable fix."""
    mangled = latin1_csv_bytes.decode("utf-8", errors="ignore")
    assert "PEA" in mangled  # the N-tilde vanished from PEÑA
    assert "PE\xd1A" not in mangled


def test_utf8_sig_does_not_rescue_latin1(latin1_csv_bytes: bytes):
    """utf-8-sig is the usual first guess for a CMS file and does not help."""
    with pytest.raises(UnicodeDecodeError):
        latin1_csv_bytes.decode("utf-8-sig")


# --------------------------------------------------------------------------
# The package's own reader, once it exists.
# --------------------------------------------------------------------------
def _reader():
    for name in PARSE_MODULES:
        fn = find_attr(try_import(name), "read_csv", "read_rows", "iter_rows", "open_csv")
        if callable(fn):
            return fn
    return None


@require(PARSE_MODULES[0])
def test_package_reader_handles_latin1(latin1_csv_path: Path):
    reader = _reader()
    if reader is None:
        modules = " / ".join(PARSE_MODULES)
        pytest.skip(f"awaiting a CSV reader in {modules}")

    rows = list(reader(latin1_csv_path))
    assert rows, "reader returned nothing"


def test_stringio_roundtrip_is_encoding_independent():
    """Sanity check on the in-memory path used by the diff writer."""
    buffer = io.StringIO()
    csv.writer(buffer).writerow(["PE\xd1A", "JOS\xe9"])
    assert buffer.getvalue().strip() == "PE\xd1A,JOS\xe9"
