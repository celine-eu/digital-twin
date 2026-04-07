"""
Enhanced Participant Domain with REC Registry integration.

Integrates RecRegistryUserClient to fetch member and community information
from the registry using the user's JWT token.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from celine.sdk.rec_registry import RecRegistryUserClient, RecRegistryAdminClient
from fastapi import HTTPException, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.contracts.ontology import OntologyFetcherBinding, OntologySpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.ontology import SPECS_DIR
from celine.dt.domains.participant.config import ParticipantDomainSettings

from celine.sdk.openapi.rec_registry.schemas import (
    UserMeResponseSchema,
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
                            "description": "Device ID mapped from participant meter ID",
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
            ValueFetcherSpec(
                id="meter_anomalies",
                client="dataset_api",
                query="""
                    SELECT
                    device_id,
                    COUNT(*) AS occurrences_last_hour
                    FROM ds_dev_gold.meters_data_15m_missing_intervals
                    WHERE created_at >= now() - INTERVAL '1 hour'
                    GROUP BY device_id
                    HAVING COUNT(*) > 3
                    ORDER BY occurrences_last_hour DESC, device_id;
                """,
                limit=1000,
            ),
            ValueFetcherSpec(
                id="meter_forecast",
                client="dataset_api",
                query="""
                    SELECT
                        device_id,
                        timestamp,
                        period,
                        total_production_kwh,
                        total_consumption_kwh,
                        net_exchange_kwh,
                        total_production_lower,
                        total_production_upper,
                        total_consumption_lower,
                        total_consumption_upper,
                        pct_autoconsumption
                    FROM ds_dev_gold.meters_energy_forecast
                    WHERE device_id = :device_id
                    AND timestamp >= :start
                    AND timestamp < :end
                    ORDER BY timestamp ASC
                """,
                limit=48,
                payload_schema={
                    "type": "object",
                    "required": ["device_id"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device ID for the meter",
                        },
                        "start": {
                            "type": "string",
                            "description": "Forecast start (ISO timestamp, defaults to now)",
                            "default": "NOW()",
                        },
                        "end": {
                            "type": "string",
                            "description": "Forecast end (ISO timestamp, defaults to now + 48h)",
                            "default": "NOW() + INTERVAL '48 hours'",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="total_meters_forecast",
                client="dataset_api",
                query="""
                    SELECT timestamp, period, production_kwh, consumption_kwh,
                           n_active_devices, net_exchange_kwh, is_surplus,
                           forecast_origin, generated_at
                    FROM ds_dev_gold.total_meters_forecast
                    WHERE timestamp >= :start
                      AND timestamp < :end
                    ORDER BY timestamp ASC
                """,
                limit=96,
                payload_schema={
                    "type": "object",
                    "required": [],
                    "additionalProperties": False,
                    "properties": {
                        "start": {
                            "type": "string",
                            "description": "Forecast start (ISO timestamp, defaults to today 05:00)",
                            "default": "date_trunc('day', NOW()) + INTERVAL '5 hours'",
                        },
                        "end": {
                            "type": "string",
                            "description": "Forecast end (ISO timestamp, defaults to tomorrow 00:00)",
                            "default": "date_trunc('day', NOW()) + INTERVAL '1 day'",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="rec_flexibility_windows",
                client="dataset_api",
                query="""
                    SELECT
                        _id,
                        window_start,
                        window_end,
                        community_kwh,
                        estimated_kwh,
                        reward_points_estimated,
                        confidence
                    FROM ds_dev_gold.rec_flexibility_windows
                    WHERE device_id = :device_id
                      AND ts_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '1 day'
                      AND window_end > NOW()
                      AND estimated_kwh >= 0.5
                    ORDER BY estimated_kwh DESC
                """,
                limit=5,
                payload_schema={
                    "type": "object",
                    "required": ["device_id"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Sensor/device ID for the participant",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="rec_virtual_consumption_per_device_15m",
                client="dataset_api",
                query="""
                    SELECT
                        ts,
                        device_id,
                        consumption_kwh,
                        ratio,
                        virtual_consumption_kwh
                    FROM ds_dev_gold.rec_virtual_consumption_per_device_15m
                    WHERE device_id = :device_id
                    AND ts >= :start
                    AND ts < :end
                    ORDER BY ts ASC
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["device_id", "start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device identifier",
                        },
                        "start": {
                            "type": "string",
                            "description": "Period start (ISO timestamp)",
                        },
                        "end": {
                            "type": "string",
                            "description": "Period end (ISO timestamp)",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="rec_settlement_1h",
                client="dataset_api",
                query="""
                    SELECT
                        ts,
                        device_id,
                        consumption_kwh,
                        window_start,
                        window_end
                    FROM ds_dev_gold.rec_settlement_1h
                    WHERE device_id = :device_id
                    AND ts >= :start
                    AND ts < :end
                    ORDER BY ts ASC
                """,
                limit=168,
                payload_schema={
                    "type": "object",
                    "required": ["device_id"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Sensor/device ID for the participant",
                        },
                        "start": {
                            "type": "string",
                            "description": "Period start (ISO timestamp, defaults to 7 days ago)",
                            "default": "NOW() - INTERVAL '7 days'",
                        },
                        "end": {
                            "type": "string",
                            "description": "Period end (ISO timestamp, defaults to now)",
                            "default": "NOW()",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="rec_participant_points",
                client="dataset_api",
                query="""
                    SELECT
                        device_id,
                        ts_date,
                        daily_consumption_kwh,
                        daily_points
                    FROM ds_dev_gold.rec_participant_points
                    WHERE device_id = :device_id
                    ORDER BY ts_date ASC
                """,
                limit=365,
                payload_schema={
                    "type": "object",
                    "required": ["device_id"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Sensor/device ID for the participant",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="rec_gamification_summary",
                client="dataset_api",
                query="""
                    SELECT
                        device_id,
                        ts_date,
                        total_consumption_kwh,
                        percentile_rank,
                        rank_position,
                        total_members
                    FROM ds_dev_gold.rec_gamification_summary
                    WHERE device_id = :device_id
                      AND ts_date = :date
                """,
                limit=1,
                payload_schema={
                    "type": "object",
                    "required": ["device_id", "date"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Sensor/device ID for the participant",
                        },
                        "date": {
                            "type": "string",
                            "description": "ISO date (YYYY-MM-DD) for the ranking snapshot",
                        },
                    },
                },
            ),
        ]

    def get_ontology_specs(self) -> list[OntologySpec]:
        """Ontology concept views for the participant domain."""
        return [
            OntologySpec(
                id="meters",
                description="Meter energy readings as SOSA observations",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="meters_data",
                        mapper_spec_path=SPECS_DIR / "obs_meter_energy.yaml",
                    )
                ],
            ),
            OntologySpec(
                id="meter_forecast",
                description="Meter energy forecast as PECO forecasts",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="meter_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_meter_forecast.yaml",
                    )
                ],
            ),
            OntologySpec(
                id="participant_snapshot",
                description="Full participant view: meter readings + energy forecast",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="meters_data",
                        mapper_spec_path=SPECS_DIR / "obs_meter_energy.yaml",
                    ),
                    OntologyFetcherBinding(
                        fetcher_id="meter_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_meter_forecast.yaml",
                    ),
                ],
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
