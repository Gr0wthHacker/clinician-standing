"""CMS DAC download-URL discovery from the metastore item.

The live metastore serves each distribution's fields flat on the distribution
object; a reference-expanded view nests them under ``data``. Both must resolve,
because reading only the nested shape is what broke discovery against the live
API -- every monthly run failed with "no CSV distribution".
"""

from __future__ import annotations

import pytest

try:  # pragma: no cover - the module is the subject of the test
    from clinician_standing.config import Settings
    from clinician_standing.connectors.base import ConnectorError
    from clinician_standing.connectors.cms_dac import CmsDacConnector
except ImportError:  # pragma: no cover
    CmsDacConnector = None  # type: ignore[assignment]


CSV_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "abc123_1787091341/DAC_NationalDownloadableFile.csv"
)


def _connector(document: object):
    c = CmsDacConnector(Settings())
    c.fetch_json = lambda _url: document  # type: ignore[method-assign]
    return c


def test_flat_distribution_shape_resolves() -> None:
    # The shape the live metastore item returns today.
    doc = {
        "modified": "2026-09-01",
        "distribution": [
            {"@type": "dcat:Distribution", "mediaType": "text/csv", "downloadURL": CSV_URL},
        ],
    }
    assert _connector(doc).discover_download_url() == CSV_URL


def test_nested_data_shape_still_resolves() -> None:
    # The reference-expanded shape, kept working for backward compatibility.
    doc = {"distribution": [{"data": {"mediaType": "text/csv", "downloadURL": CSV_URL}}]}
    assert _connector(doc).discover_download_url() == CSV_URL


def test_non_csv_distribution_is_skipped() -> None:
    doc = {
        "distribution": [
            {"mediaType": "application/pdf", "downloadURL": "https://data.cms.gov/x.pdf"},
        ]
    }
    with pytest.raises(ConnectorError):
        _connector(doc).discover_download_url()


def test_csv_by_extension_when_media_type_absent() -> None:
    doc = {"distribution": [{"downloadURL": CSV_URL}]}
    assert _connector(doc).discover_download_url() == CSV_URL
