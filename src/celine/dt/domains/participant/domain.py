# celine/dt/domains/participant/base.py
"""
Participant domain – individual member-level Digital Twin.

Provides per-participant data access and simulations scoped to a
single member of an energy community.

Route surface::

    /participants/{participant_id}/values/...
    /participants/{participant_id}/simulations/...
    /participants/{participant_id}/profile
    /participants/{participant_id}/flexibility
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from fastapi import APIRouter, HTTPException, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain

logger = logging.getLogger(__name__)


class ParticipantDomain(DTDomain):
    """Base participant domain.

    Each participant entity implicitly belongs to a community. The
    ``community_id`` is expected in the entity metadata (populated
    by ``resolve_entity`` or carried in the underlying data).
    """

    domain_type: ClassVar[str] = "participant"
    route_prefix: ClassVar[str] = "/participants"
    entity_id_param: ClassVar[str] = "participant_id"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [
            ValueFetcherSpec(
                id="meter_readings",
                client="dataset_api",
                query="""
                    SELECT timestamp, channel, kwh, direction
                    FROM meter_readings
                    WHERE participant_id = '{{ entity.id }}'
                      AND timestamp >= :start
                      AND timestamp < :end
                    ORDER BY timestamp
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                },
            ),
            ValueFetcherSpec(
                id="assets",
                client="dataset_api",
                query="""
                    SELECT asset_id, asset_type, capacity_kw, installed_at
                    FROM participant_assets
                    WHERE participant_id = '{{ entity.id }}'
                    ORDER BY installed_at
                """,
                limit=100,
            ),
            ValueFetcherSpec(
                id="consumption_profile",
                client="dataset_api",
                query="""
                    SELECT hour_of_day, avg_kwh, stddev_kwh
                    FROM consumption_profiles
                    WHERE participant_id = '{{ entity.id }}'
                    ORDER BY hour_of_day
                """,
                limit=24,
            ),
        ]

    def routes(self) -> APIRouter:
        router = APIRouter()
        domain = self

        @router.get("/profile")
        async def participant_profile(
            participant_id: str,
            request: Request,
        ) -> dict[str, Any]:
            """Participant profile and metadata."""
            entity = await domain.resolve_entity(participant_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Participant not found")
            return {
                "participant_id": entity.id,
                "domain": domain.name,
                "metadata": entity.metadata,
            }

        @router.get("/flexibility")
        async def flexibility(
            participant_id: str,
            request: Request,
        ) -> dict[str, Any]:
            """Flexibility assessment for demand response.

            Placeholder for real flexibility computation.
            """
            entity = await domain.resolve_entity(participant_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Participant not found")
            return {
                "participant_id": entity.id,
                "flexible_load_kw": None,
                "available_window_hours": None,
                "note": "Implement with actual flexibility analysis",
            }

        return router

    async def on_startup(self) -> None:
        logger.info(
            "ParticipantDomain '%s' starting (type=%s, version=%s)",
            self.name, self.domain_type, self.version,
        )


class ITParticipantDomain(ParticipantDomain):
    """Italian participant domain."""

    name: ClassVar[str] = "it-participant"
    version: ClassVar[str] = "1.0.0"


# Module-level instance for the domain loader
domain = ITParticipantDomain()
