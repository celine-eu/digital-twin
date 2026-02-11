"""
Enhanced Participant Domain with REC Registry integration.

Integrates RecRegistryUserClient to fetch member and community information
from the registry using the user's JWT token.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from celine.sdk.auth import JwtUser
from celine.sdk.rec_registry import RecRegistryUserClient
from fastapi import APIRouter, Depends, HTTPException, Request

from celine.dt.api.dependencies import get_jwt_user
from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.domains.participant.config import ParticipantDomainSettings

from celine.sdk.openapi.rec_registry.schemas import (
    UserMeResponseSchema,
    UserCommunityDetailSchema,
    UserMemberDetailSchema,
    UserAssetsResponseSchema,
    UserDeliveryPointsResponseSchema,
)

logger = logging.getLogger(__name__)


class ParticipantDomain(DTDomain):
    """Base participant domain with REC Registry integration.

    Resolves participant entities by querying the registry with the user's JWT.
    Enriches entity metadata with member and community information.
    """

    domain_type: ClassVar[str] = "participant"
    route_prefix: ClassVar[str] = "/participants"
    entity_id_param: ClassVar[str] = "participant_id"

    def __init__(self, settings: ParticipantDomainSettings | None = None, **kwargs):
        """Initialize with registry client.

        Args:
            registry_base_url: Base URL for REC Registry API
        """
        super().__init__(**kwargs)

        self.settings = settings or ParticipantDomainSettings()

        # Initialize registry client ONCE - reused for all requests
        self._registry_client = RecRegistryUserClient(
            base_url=self.settings.registry_base_url,
            timeout=self.settings.registry_timeout or 5,
        )

    @property
    def rec_registry(self):
        return self._registry_client

    async def get_participant(self, request: Request) -> UserMeResponseSchema | None:

        jwt_token = request.headers.get("authorization", "").replace("Bearer ", "")
        if jwt_token is None:
            logger.warning("No JWT token provided for participant resolution")
            return None

        try:
            # Get user profile from registry (includes member info)
            participant = await self._registry_client.get_me(token=jwt_token)

            if not participant:
                logger.warning("User is not a participant")
                return None

            return participant
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to resolve participant from registry: %s", exc)
            return None

    async def resolve_entity(
        self, entity_id: str, request: Request
    ) -> EntityInfo | None:
        """Resolve participant entity from registry.

        Queries the registry to validate the participant exists and enriches
        metadata with member and community information.

        Args:
            entity_id: Participant ID from URL
            jwt_token: User JWT token for registry authentication

        Returns:
            EntityInfo with member/community metadata, or None if not found
        """
        try:

            # Get user profile from registry (includes member info)
            participant = await self.get_participant(request)

            if not participant:
                logger.warning("User is not a participant")
                return None

            if not participant.membership:
                logger.warning("User has no membership details")
                return None

            # Validate this user can access the requested participant
            member = participant.membership.member
            if not member:
                logger.warning("User has no member association")
                return None

            # Get community details
            community = participant.membership.community

            # Build enriched entity
            return EntityInfo(
                id=entity_id,
                domain_name=self.name,
                metadata={
                    "member_key": member.key,
                    "member_name": member.name,
                    "user_id": participant.profile.sub,
                    "email": participant.profile.email,
                    "community_key": community.key if community else None,
                    "community_name": community.name if community else None,
                    "registry_data": {
                        "member": member,
                        "community": community,
                    },
                },
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to resolve participant from registry: %s", exc)
            return None

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        """Define data fetchers with community context."""
        return [
            ValueFetcherSpec(
                id="meter_readings",
                client="dataset_api",
                query="""
                    SELECT timestamp, channel, kwh, direction
                    FROM meter_readings
                    WHERE participant_id = '{{ entity.id }}'
                      AND community_id = '{{ entity.metadata.community_key }}'
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
                      AND community_id = '{{ entity.metadata.community_key }}'
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
                      AND community_id = '{{ entity.metadata.community_key }}'
                    ORDER BY hour_of_day
                """,
                limit=24,
            ),
        ]

    # def routes(self) -> APIRouter:
    #     """Define participant-specific routes with registry integration."""
    #     router = APIRouter()
    #     domain = self

    #     @router.get("/profile")
    #     async def participant_profile(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> UserMeResponseSchema:
    #         """Get participant profile from registry.

    #         Returns enriched profile with member and community details.
    #         """
    #         # Resolve entity using registry

    #         participant = await domain.get_participant(request)
    #         if participant is None:
    #             raise HTTPException(
    #                 status_code=404, detail="Participant not found or access denied"
    #             )

    #         return participant

    #     @router.get("/community")
    #     async def participant_community(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> UserCommunityDetailSchema:
    #         """Get participant's community details from registry."""
    #         token = request.headers.get("authorization", "").replace("Bearer ", "")

    #         # Get community via registry client
    #         try:
    #             community = await domain._registry_client.get_my_community(token=token)
    #             if community is None:
    #                 raise HTTPException(
    #                     status_code=404,
    #                     detail="Participant community not found or access denied",
    #                 )
    #             return community
    #         except HTTPException:
    #             raise
    #         except Exception as exc:
    #             logger.error("Failed to fetch community: %s", exc)
    #             raise HTTPException(
    #                 status_code=500, detail="Failed to fetch community details"
    #             )

    #     @router.get("/member")
    #     async def participant_member(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> UserMemberDetailSchema:
    #         """Get participant's member details from registry."""
    #         token = request.headers.get("authorization", "").replace("Bearer ", "")

    #         try:
    #             member = await domain._registry_client.get_my_member(token=token)
    #             if member is None:
    #                 raise HTTPException(
    #                     status_code=404,
    #                     detail="Participant membership not found or access denied",
    #                 )
    #             return member
    #         except HTTPException:
    #             raise
    #         except Exception as exc:
    #             logger.error("Failed to fetch member: %s", exc)
    #             raise HTTPException(
    #                 status_code=500, detail="Failed to fetch member details"
    #             )

    #     @router.get("/assets")
    #     async def participant_assets(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> UserAssetsResponseSchema:
    #         """Get participant's assets from registry."""
    #         token = request.headers.get("authorization", "").replace("Bearer ", "")

    #         try:
    #             assets = await domain._registry_client.get_my_assets(token=token)
    #             if assets is None:
    #                 raise HTTPException(
    #                     status_code=404,
    #                     detail="Participant assets not found or access denied",
    #                 )
    #             return assets
    #         except HTTPException:
    #             raise
    #         except Exception as exc:
    #             logger.error("Failed to fetch assets: %s", exc)
    #             raise HTTPException(
    #                 status_code=500, detail="Failed to fetch asset details"
    #             )

    #     @router.get("/delivery-points")
    #     async def participant_delivery_points(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> UserDeliveryPointsResponseSchema:
    #         """Get participant's delivery points from registry."""
    #         token = request.headers.get("authorization", "").replace("Bearer ", "")

    #         try:
    #             delivery_points = await domain._registry_client.get_my_delivery_points(
    #                 token=token
    #             )
    #             if delivery_points is None:
    #                 raise HTTPException(
    #                     status_code=404,
    #                     detail="Participant delivery points not found or access denied",
    #                 )
    #             return delivery_points
    #         except HTTPException:
    #             raise
    #         except Exception as exc:
    #             logger.error("Failed to fetch delivery points: %s", exc)
    #             raise HTTPException(
    #                 status_code=500, detail="Failed to fetch delivery point details"
    #             )

    #     @router.get("/flexibility")
    #     async def flexibility(
    #         participant_id: str,
    #         request: Request,
    #         user: JwtUser = Depends(get_jwt_user),
    #     ) -> dict[str, Any]:
    #         """Flexibility assessment for demand response.

    #         Combines registry data with local calculations.
    #         """
    #         token = request.headers.get("authorization", "").replace("Bearer ", "")
    #         entity = await domain.resolve_entity(participant_id, request)

    #         if entity is None:
    #             raise HTTPException(status_code=404, detail="Participant not found")

    #         # TODO: Implement actual flexibility calculation
    #         # Could use entity.metadata.community_key to query time-series data
    #         return {
    #             "participant_id": entity.id,
    #             "community_key": entity.metadata.get("community_key"),
    #             "flexible_load_kw": None,
    #             "available_window_hours": None,
    #             "note": "Implement with actual flexibility analysis",
    #         }

    #     return router

    async def on_startup(self) -> None:
        """Initialize domain on startup."""
        logger.info(
            "ParticipantDomain '%s' starting with registry integration (type=%s, version=%s)",
            self.name,
            self.domain_type,
            self.version,
        )


class ITParticipantDomain(ParticipantDomain):
    """Italian participant domain with registry integration."""

    name: ClassVar[str] = "it-participant"
    version: ClassVar[str] = "2.0.0"  # Bumped for registry integration


# Module-level instance factory
def create_domain(registry_base_url: str) -> ITParticipantDomain:
    """Create IT participant domain instance.

    Args:
        registry_base_url: REC Registry API base URL

    Returns:
        Configured domain instance

    Example:
        # In config/domains.yaml or startup code
        domain = create_domain(registry_base_url="https://registry.example.com")
    """
    return ITParticipantDomain()


domain = ITParticipantDomain()
