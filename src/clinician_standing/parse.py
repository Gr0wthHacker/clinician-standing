"""CSV reading for the federal bulk files.

Encoding is the whole point of this module. Two of the three Tier 1 files are
**latin-1, not UTF-8**:

* ``oig.hhs.gov/exclusions/downloadables/UPDATED.csv`` (OIG LEIE)
* the CMS Revalidation Clinic Group Practice Reassignment file

Reading either with Python's default encoding raises
``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa0``. 0xa0 is a
non-breaking space sitting inside a name or a legal business name. On the
September 2026 revalidation file the first one appears at byte 7,275, which is
far enough in to look like a truncated download rather than an encoding bug.

``errors="ignore"`` is not the fix. It silently drops the offending character,
so ``PEÑA`` becomes ``PEA`` -- a corrupted name in an exclusions file, which is
the worst place to corrupt a name. latin-1 maps every byte 0x00-0xff, so it
round-trips losslessly and can never raise.

The CMS Doctors and Clinicians file is the exception: it is UTF-8 with a byte
order mark, so it is read as ``utf-8-sig``.
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "LATIN1",
    "UTF8_BOM",
    "DecodeStats",
    "decode_lines",
    "detect_encoding",
    "read_csv",
    "read_rows",
]

#: Encoding for the OIG LEIE and CMS revalidation files.
LATIN1 = "latin-1"

#: Encoding for the CMS Doctors and Clinicians file, which carries a BOM.
UTF8_BOM = "utf-8-sig"

_PROBE_BYTES = 1 << 20


def detect_encoding(path: Path, probe_bytes: int = _PROBE_BYTES) -> str:
    """Choose an encoding for ``path``: ``utf-8-sig`` if it decodes, else latin-1.

    Connectors normally state their encoding outright, because a file that
    happens to contain no high bytes this month will still contain them next
    month. This helper exists for ad hoc reads and for the free roster audit,
    where the file is whatever a client sent.

    Args:
        path: File to probe.
        probe_bytes: How many leading bytes to test.

    Returns:
        ``utf-8-sig`` or ``latin-1``.
    """
    with path.open("rb") as handle:
        head = handle.read(probe_bytes)
    try:
        head.decode(UTF8_BOM)
    except UnicodeDecodeError:
        return LATIN1
    return UTF8_BOM


def read_csv(
    path: Path | str,
    encoding: str | None = None,
    *,
    delimiter: str = ",",
) -> Iterator[dict[str, Any]]:
    """Stream a delimited file as dicts, with the encoding handled explicitly.

    Args:
        path: File to read.
        encoding: Explicit encoding. When omitted, :func:`detect_encoding`
            picks between ``utf-8-sig`` and ``latin-1``. It never falls back to
            ``errors="ignore"``.
        delimiter: Field delimiter.

    Yields:
        One dict per data row, keyed by the header names exactly as published.
    """
    path = Path(path)
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    resolved = encoding or detect_encoding(path)
    with path.open("r", encoding=resolved, newline="") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


@dataclass
class DecodeStats:
    """Counts kept by :func:`decode_lines`, for the evidence summary."""

    lines: int = 0
    latin1_lines: int = 0


def decode_lines(raw_lines: Iterable[bytes], stats: DecodeStats | None = None) -> Iterator[str]:
    """Decode a byte-line stream as UTF-8, falling back to latin-1 per line.

    For files whose encoding is not stated by the publisher and too large to
    probe usefully -- the NPPES replicate is ~9 GB uncompressed, and a single
    latin-1 byte at line six million would crash a UTF-8 reader after half an
    hour. Each line is tried as UTF-8 first (the BOM is stripped from the first
    line) and decoded as latin-1 only if that fails, so a UTF-8 file round-trips
    exactly and a stray latin-1 byte costs one line's worth of mojibake at worst,
    never a dropped character and never an exception. Same rule as the module
    docstring: no ``errors="ignore"``.

    The result is fed to ``csv.reader``, which reassembles quoted fields that
    span lines, so splitting on newlines here is safe.

    Args:
        raw_lines: Binary lines, e.g. iterating a file opened ``rb`` or a zip
            member.
        stats: Optional counters, updated in place.

    Yields:
        Decoded text lines, line endings preserved.
    """
    first = True
    for raw in raw_lines:
        if first:
            first = False
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
        if stats is not None:
            stats.lines += 1
        try:
            yield raw.decode("utf-8")
        except UnicodeDecodeError:
            if stats is not None:
                stats.latin1_lines += 1
            yield raw.decode(LATIN1)


#: Alias kept because "read_rows" reads better at call sites that stream.
read_rows = read_csv
