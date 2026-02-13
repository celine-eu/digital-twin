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
                id="meters_data",
                client="dataset_api",
                query="""
                    SELECT 
                        _id,
                        device_id,
                        ts,
                        consumption_kw,
                        production_kw,
                        self_consumed_kw
                    FROM ds_dev_gold.meters_data_15m
                    WHERE device_id = :device_id
                    AND ts >= :start
                    AND ts < :end
                    ORDER BY ts DESC
                """,
                limit=1000,
                payload_schema={
                    "type": "object",
                    "required": ["device_id"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device ID mapped from participant meter ID (e.g., 'c2g-57CFAAA3C')",
                        },
                        "start": {
                            "type": "string",
                            "description": "ISO timestamp for range start (defaults to 12 hours ago)",
                            "default": "NOW() - INTERVAL '12 hours'",
                        },
                        "end": {
                            "type": "string",
                            "description": "ISO timestamp for range end (defaults to now)",
                            "default": "NOW()",
                        },
                    },
                },
            ),
        ]

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
