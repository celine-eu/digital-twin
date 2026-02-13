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
        """Default community value fetchers.

        These use Jinja templates with ``{{ entity.id }}`` for automatic
        entity scoping. Override or extend in subclass.
        """
        return []

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
