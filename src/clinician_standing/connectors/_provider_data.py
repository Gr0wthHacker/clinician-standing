"""Shared helpers for CMS Provider Data Catalog files.

The DAC, Facility Affiliation and Hospital General Information files are all
datasets in the CMS provider-data metastore, and all of them move their CSV to
a new content-hashed URL every release. :func:`discover_csv` resolves the
current URL from the dataset's metastore item. The DAC connector predates this
module and keeps its own copy of the same logic; it has a regression test of
its own (``tests/test_cms_dac_discovery.py``) and is left alone.
"""

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..parse import DecodeStats, decode_lines
from .base import Connector, ConnectorError

__all__ = [
    "METASTORE_ITEM",
    "CatalogEntry",
    "discover_csv",
    "normalize_ccn",
    "open_csv",
]

#: Metastore item URL for a provider-data dataset identifier.
METASTORE_ITEM = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{id}"

_CCN = re.compile(r"^[0-9A-Z]{6}$")


@dataclass(frozen=True)
class CatalogEntry:
    """What the metastore says about the current release."""

    dataset_id: str
    url: str
    modified: str | None


def discover_csv(connector: Connector, dataset_id: str) -> CatalogEntry:
    """Resolve the current CSV download for a provider-data dataset.

    Accepts both distribution shapes the metastore serves: fields flat on the
    distribution (the live item endpoint) and nested under ``data`` (the
    reference-expanded view). Reading only one of them is how DAC discovery
    broke once.

    Args:
        connector: The calling connector, for its allowlisted HTTP and logger.
        dataset_id: Provider-data identifier, e.g. ``27ea-46a8``.

    Returns:
        The current entry, URL already checked against the allowlist.

    Raises:
        ConnectorError: If the item has no CSV distribution.
    """
    item_url = METASTORE_ITEM.format(id=dataset_id)
    document = connector.fetch_json(item_url)
    if not isinstance(document, dict):
        raise ConnectorError(f"{item_url} did not return a dataset object")
    modified = document.get("modified")
    for distribution in document.get("distribution", []) or []:
        data = distribution.get("data") or distribution
        media_type = (data.get("mediaType") or "").lower()
        url = data.get("downloadURL")
        if url and (media_type == "text/csv" or str(url).lower().endswith(".csv")):
            connector.log.info("%s distribution: %s (modified %s)", dataset_id, url, modified)
            return CatalogEntry(
                dataset_id=dataset_id,
                url=connector.require_allowed_url(str(url)),
                modified=str(modified) if modified else None,
            )
    raise ConnectorError(f"no CSV distribution in the metastore item at {item_url}")


@contextmanager
def open_csv(path: Path, stats: DecodeStats) -> Iterator[csv.DictReader[str]]:
    """Open a provider-data CSV as a DictReader, encoding-safe.

    Provider-data files are UTF-8, most with a BOM. They are read through
    :func:`clinician_standing.parse.decode_lines` anyway, so a stray latin-1
    byte in a facility name costs one line of mojibake rather than the run.
    """
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with path.open("rb") as handle:
        yield csv.DictReader(decode_lines(handle, stats))


def normalize_ccn(value: str | None) -> str | None:
    """Normalize a CMS Certification Number, or return None if it is not one.

    CCNs are six characters, digits plus the occasional letter in the third
    position for units (``33T241``). A numeric CCN that lost its leading zeros
    on a trip through a spreadsheet is padded back; anything else that does not
    fit the pattern is rejected rather than loaded, because the tables carry a
    CHECK and one bad value would abort the transaction.
    """
    raw = (value or "").strip().upper()
    if raw.isdigit() and 0 < len(raw) < 6:
        raw = raw.zfill(6)
    return raw if _CCN.match(raw) else None
