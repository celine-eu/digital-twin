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
        return [
            ValueFetcherSpec(
                id="consumption_timeseries",
                client="dataset_api",
                query="""
                    SELECT timestamp, participant_id, kwh
                    FROM consumption
                    WHERE community_id = '{{ entity.id }}'
                      AND timestamp >= :start
                      AND timestamp < :end
                    ORDER BY timestamp
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "start": {"type": "string", "description": "ISO timestamp"},
                        "end": {"type": "string", "description": "ISO timestamp"},
                    },
                },
            ),
            ValueFetcherSpec(
                id="generation_timeseries",
                client="dataset_api",
                query="""
                    SELECT timestamp, asset_id, kwh
                    FROM generation
                    WHERE community_id = '{{ entity.id }}'
                      AND timestamp >= :start
                      AND timestamp < :end
                    ORDER BY timestamp
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                },
            ),
            ValueFetcherSpec(
                id="participants",
                client="dataset_api",
                query="""
                    SELECT participant_id, name, role, joined_at
                    FROM participants
                    WHERE community_id = '{{ entity.id }}'
                    ORDER BY joined_at
                """,
                limit=500,
            ),
        ]

    # -- custom routes ---------------------------------------------------

    def routes(self) -> APIRouter:
        router = APIRouter()
        domain = self  # capture for closures

        @router.get("/energy-balance")
        async def energy_balance(
            community_id: str,
            request: Request,
            start: str | None = None,
            end: str | None = None,
        ) -> dict[str, Any]:
            """Compute current energy balance for the community.

            This is a sample custom endpoint. A real implementation would
            fetch consumption + generation timeseries and compute metrics.
            """
            entity = await domain.resolve_entity(community_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Community not found")

            # Placeholder – real logic fetches data and computes
            return {
                "community_id": entity.id,
                "domain": domain.name,
                "start": start,
                "end": end,
                "self_consumption_ratio": None,
                "self_sufficiency_ratio": None,
                "note": "Implement with actual data fetching",
            }

        @router.get("/summary")
        async def community_summary(
            community_id: str, request: Request
        ) -> dict[str, Any]:
            """High-level community summary."""
            entity = await domain.resolve_entity(community_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Community not found")

            return {
                "community_id": entity.id,
                "domain": domain.name,
                "domain_type": domain.domain_type,
                "version": domain.version,
                "metadata": entity.metadata,
            }

        return router

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
