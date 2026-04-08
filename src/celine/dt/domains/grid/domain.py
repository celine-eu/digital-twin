# celine/dt/domains/grid/domain.py
"""
Grid resilience domain — weather-driven risk monitoring for MT distribution networks.

Route surface::

    /grid/{network_id}/wind/map
    /grid/{network_id}/wind/bosco
    /grid/{network_id}/wind/alert-distribution
    /grid/{network_id}/wind/trend
    /grid/{network_id}/heat/map
    /grid/{network_id}/heat/alert-distribution
    /grid/{network_id}/heat/trend
"""
from __future__ import annotations

import logging
from typing import ClassVar

from celine.dt.core.domain.base import DTDomain
from celine.dt.core.clients.dataset_api import DatasetSqlApiClient

logger = logging.getLogger(__name__)


class GridDomain(DTDomain):
    """Grid resilience domain.

    Pure read-through domain: no participant/asset/ontology machinery.
    Surfaces filtered GeoJSON and aggregated risk data from ds_dev_gold tables.
    """

    domain_type: ClassVar[str] = "grid"
    route_prefix: ClassVar[str] = "/grid"
    entity_id_param: ClassVar[str] = "network_id"

    @property
    def dataset_client(self) -> DatasetSqlApiClient:
        return self.infra.clients_registry.get("dataset_api")

    async def on_startup(self) -> None:
        logger.info(
            "GridDomain '%s' starting (type=%s, version=%s)",
            self.name,
            self.domain_type,
            self.version,
        )


class ITGridDomain(GridDomain):
    """Italian MT grid resilience domain."""

    name: ClassVar[str] = "it-grid"
    version: ClassVar[str] = "1.0.0"


domain = ITGridDomain()
