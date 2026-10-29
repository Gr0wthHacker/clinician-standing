"""Source connectors and their registry.

Adding a connector means adding it to :data:`CONNECTORS`; the CLI, the source
registry seeding and ``ingest all`` all read from there.
"""

from __future__ import annotations

from collections.abc import Mapping

from .base import Connector, ConnectorError, DiffResult, RunResult
from .cms_dac import CmsDacConnector
from .cms_facility_affiliation import CmsFacilityAffiliationConnector
from .cms_hospitals import CmsHospitalsConnector
from .cms_revalidation import CmsRevalidationConnector
from .nppes import NppesConnector
from .nppes_weekly import NppesWeeklyConnector
from .nursys import NursysConnector
from .oig_leie import OigLeieConnector

__all__ = [
    "CONNECTORS",
    "CmsDacConnector",
    "CmsFacilityAffiliationConnector",
    "CmsHospitalsConnector",
    "CmsRevalidationConnector",
    "Connector",
    "ConnectorError",
    "DiffResult",
    "NppesConnector",
    "NppesWeeklyConnector",
    "NursysConnector",
    "OigLeieConnector",
    "RunResult",
    "connector_keys",
    "get_connector",
]

#: Registry key -> connector class. Order matters for ``ingest all``: the DAC
#: file creates the practices and clinicians that the other connectors join to,
#: so nursys (which derives licenses for already-enrolled clinicians) runs last.
#: The directory connectors (nppes, cms_hospitals, cms_facility_affiliation)
#: write reference tables keyed on NPI and CCN and depend on nothing. nppes and
#: nppes_weekly run before oig_leie because the LEIE load matches its rows that
#: carry no NPI against nppes_providers by name and state; hospitals run before
#: the affiliations that point at them.
CONNECTORS: Mapping[str, type[Connector]] = {
    CmsDacConnector.key: CmsDacConnector,
    CmsRevalidationConnector.key: CmsRevalidationConnector,
    NppesConnector.key: NppesConnector,
    NppesWeeklyConnector.key: NppesWeeklyConnector,
    OigLeieConnector.key: OigLeieConnector,
    CmsHospitalsConnector.key: CmsHospitalsConnector,
    CmsFacilityAffiliationConnector.key: CmsFacilityAffiliationConnector,
    NursysConnector.key: NursysConnector,
}


def connector_keys() -> list[str]:
    """Return every registered connector key in run order."""
    return list(CONNECTORS)


def get_connector(key: str) -> type[Connector]:
    """Look up a connector class by registry key.

    Args:
        key: A value from :data:`CONNECTORS`.

    Returns:
        The connector class.

    Raises:
        KeyError: If the key is not registered.
    """
    try:
        return CONNECTORS[key]
    except KeyError as exc:
        raise KeyError(f"unknown connector {key!r}; known keys: {', '.join(CONNECTORS)}") from exc
