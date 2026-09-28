# celine/dt/domains/energy_community/base.py
"""
Energy Community domain – base class for community-level Digital Twins.

This provides the shared structure for energy community DTs across
regulatory regimes. Locale variants (IT, DE, etc.) inherit from this
and override incentive models, data sources, and regulatory logic.

Route surface::

    /communities/{community_id}/values/...
    /communities/{community_id}/simulations/...
    /communities/{community_id}/energy-balance
    /communities/{community_id}/summary
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from fastapi import APIRouter, HTTPException, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.simulation import DTSimulation
from celine.dt.contracts.subscription import SubscriptionSpec
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.context import RunContext
from celine.dt.core.domain.base import DTDomain
from celine.dt.domains.energy_community.boundary_fetchers import boundary_value_specs

logger = logging.getLogger(__name__)


class EnergyCommunityDomain(DTDomain):
    """Base energy community domain.

    Subclass and override for locale-specific behaviour. At minimum,
    override ``get_value_specs`` to provide the right data queries
    and ``get_simulations`` for the planning model.
    """

    domain_type: ClassVar[str] = "energy-community"
    route_prefix: ClassVar[str] = "/communities"
    entity_id_param: ClassVar[str] = "community_id"

    # -- values (override in locale subclass) ----------------------------

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        """Community value fetchers every locale shares.

        The reference-boundary fetchers (``boundary_at_point``,
        ``boundary_shape``; ADR-0003) live here so each locale variant inherits
        them. A subclass extends this list with ``super().get_value_specs()``
        rather than replacing it.
        """
        return boundary_value_specs()

    # -- lifecycle -------------------------------------------------------

    async def on_startup(self) -> None:
        logger.info(
            "EnergyCommunityDomain '%s' starting (type=%s, version=%s)",
            self.name,
            self.domain_type,
            self.version,
        )

    async def on_shutdown(self) -> None:
        logger.info("EnergyCommunityDomain '%s' shutting down", self.name)
