# celine/dt/domains/energy_community/domain.py
"""
Italian Renewable Energy Community (REC) domain.

Extends the base EnergyCommunityDomain with Italian-specific:
* GSE incentive model values
* Italian regulatory parameters
* REC planning simulation
"""
from __future__ import annotations

import logging
from typing import ClassVar

from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.contracts.ontology import OntologyFetcherBinding, OntologySpec
from celine.dt.core.ontology import SPECS_DIR
from celine.dt.domains.energy_community.base import EnergyCommunityDomain

logger = logging.getLogger(__name__)


class ITEnergyCommunityDomain(EnergyCommunityDomain):
    """Italian REC domain implementation."""

    name: ClassVar[str] = "it-energy-community"
    version: ClassVar[str] = "1.0.0"
    route_prefix: ClassVar[str] = "/communities/it"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        """Italian REC value fetchers.

        Extends base community fetchers with Italy-specific data sources.
        """
        base = super().get_value_specs()
        italian_specific = [
            ValueFetcherSpec(
                id="rec_self_consumption",
                client="dataset_api",
                query="""
                    SELECT 
                        ts,
                        total_consumption_kw,
                        total_production_kw,
                        self_consumption_kw,
                        self_consumption_ratio
                    FROM ds_dev_gold.rec_virtual_consumption_15m
                    WHERE ts >= :start
                    AND ts < :end
                    ORDER BY ts ASC
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
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
                id="weather_forecast_hourly",
                client="dataset_api",
                query="""
                    SELECT 
                        ts,
                        temp,
                        humidity,
                        pressure,
                        uvi,
                        clouds,
                        wind_deg,
                        weather_main,
                        weather_description,
                        lat,
                        lon
                    FROM ds_dev_gold.folgaria_weather_hourly
                    WHERE location_id = :location_id
                    AND ts >= :forecast_date::date
                    AND ts < :forecast_date::date + INTERVAL '1 day'
                    ORDER BY ts ASC
                """,
                limit=48,
                payload_schema={
                    "type": "object",
                    "required": ["location_id", "forecast_date"],
                    "additionalProperties": False,
                    "properties": {
                        "location_id": {
                            "type": "string",
                            "description": "Location identifier (e.g., 'it_folgaria')",
                        },
                        "forecast_date": {
                            "type": "string",
                            "description": "Date for forecast in ISO format (YYYY-MM-DD)",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="pv_potential_forecast",
                client="dataset_api",
                query="""
                    SELECT
                        provider,
                        run_time_utc,
                        forecast_time_utc,
                        lat,
                        lon,
                        asob_s_wm2,
                        performance_ratio,
                        pv_kwh_per_kwp_hourly
                    FROM ds_dev_gold.pv_potential_forecast_hourly
                    WHERE lat BETWEEN {{ entity.metadata.lat | default(45.7) }} - 0.05
                                AND {{ entity.metadata.lat | default(45.7) }} + 0.05
                    AND lon BETWEEN {{ entity.metadata.lon | default(10.52) }} - 0.05
                                AND {{ entity.metadata.lon | default(10.52) }} + 0.05
                    AND forecast_time_utc >= :start
                    AND forecast_time_utc < :end
                    ORDER BY forecast_time_utc ASC
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "start": {
                            "type": "string",
                            "description": "Forecast period start (ISO timestamp, e.g., start of today)",
                        },
                        "end": {
                            "type": "string",
                            "description": "Forecast period end (ISO timestamp, e.g., end of tomorrow)",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="weather_current",
                client="dataset_api",
                query="""
                    SELECT
                        ts,
                        temp,
                        humidity,
                        uvi,
                        clouds,
                        wind_deg,
                        sunrise,
                        sunset,
                        weather_main,
                        weather_description
                    FROM ds_dev_gold.folgaria_weather_current
                    WHERE location_id = :location_id
                    ORDER BY ts DESC
                """,
                limit=1,
                payload_schema={
                    "type": "object",
                    "required": ["location_id"],
                    "additionalProperties": False,
                    "properties": {
                        "location_id": {
                            "type": "string",
                            "description": "Location identifier (e.g., 'it_folgaria')",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="weather_daily",
                client="dataset_api",
                query="""
                    SELECT
                        ts,
                        temp_day,
                        temp_min,
                        temp_max,
                        pop,
                        rain,
                        clouds,
                        uvi,
                        weather_main,
                        weather_description,
                        summary,
                        sunrise,
                        sunset
                    FROM ds_dev_gold.folgaria_weather_daily
                    WHERE location_id = :location_id
                    AND ts >= :start
                    AND ts < :end
                    ORDER BY ts ASC
                """,
                limit=14,
                payload_schema={
                    "type": "object",
                    "required": ["location_id", "start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "location_id": {
                            "type": "string",
                            "description": "Location identifier (e.g., 'it_folgaria')",
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
                id="weather_alerts",
                client="dataset_api",
                query="""
                    SELECT
                        sender_name,
                        event,
                        start_ts,
                        end_ts,
                        description
                    FROM ds_dev_gold.folgaria_weather_alerts
                    WHERE location_id = :location_id
                    AND end_ts > now()
                    ORDER BY start_ts ASC
                """,
                limit=20,
                payload_schema={
                    "type": "object",
                    "required": ["location_id"],
                    "additionalProperties": False,
                    "properties": {
                        "location_id": {
                            "type": "string",
                            "description": "Location identifier (e.g., 'it_folgaria')",
                        },
                    },
                },
            ),
            ValueFetcherSpec(
                id="weather_irradiance_hourly",
                client="dataset_api",
                query="""
                    SELECT
                        datetime,
                        shortwave_radiation,
                        diffuse_radiation,
                        global_tilted_irradiance,
                        cloud_cover
                    FROM ds_dev_silver.om_weather_hourly
                    WHERE datetime >= :start
                    AND datetime < :end
                    ORDER BY datetime ASC
                """,
                limit=48,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
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
                id="rec_forecast",
                client="dataset_api",
                query="""
                    SELECT
                        datetime,
                        prediction,
                        period,
                        lower,
                        upper
                    FROM ds_dev_gold.cer_energy_forecast
                    WHERE datetime >= :start
                    AND datetime < :end
                    ORDER BY datetime ASC
                """,
                limit=48,
                payload_schema={
                    "type": "object",
                    "required": ["start", "end"],
                    "additionalProperties": False,
                    "properties": {
                        "start": {
                            "type": "string",
                            "description": "Forecast start (ISO timestamp)",
                        },
                        "end": {
                            "type": "string",
                            "description": "Forecast end (ISO timestamp)",
                        },
                    },
                },
            ),
            # Service-to-service fetcher used by flexibility-api settlement.
            # Returns hourly actual consumption for a specific device within a
            # committed flexibility window.  Caller sums consumption_kwh
            # to obtain actual kWh; reward_points_actual = round(sum × 10).
            # Access control: dataset-api Rego (access_level: internal,
            # requires dataset.query scope for service accounts).
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
                    AND ts >= :window_start
                    AND ts < :window_end
                    ORDER BY ts ASC
                """,
                limit=24,
                payload_schema={
                    "type": "object",
                    "required": ["device_id", "window_start", "window_end"],
                    "additionalProperties": False,
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device identifier",
                        },
                        "window_start": {
                            "type": "string",
                            "description": "Window start (ISO timestamp)",
                        },
                        "window_end": {
                            "type": "string",
                            "description": "Window end (ISO timestamp)",
                        },
                    },
                },
            ),
            # Service-to-service fetcher used by flexibility-api settlement.
            # Returns all devices' gamification data for a given date.
            # Access control is enforced by dataset-api (access_level: internal,
            # requires dataset.query scope for service accounts).
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
                    WHERE ts_date = :date
                """,
                limit=500,
                payload_schema={
                    "type": "object",
                    "required": ["date"],
                    "additionalProperties": False,
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "ISO date (YYYY-MM-DD) for the gamification snapshot",
                        },
                    },
                },
            ),
        ]
        return base + italian_specific

    def get_ontology_specs(self) -> list[OntologySpec]:
        """Ontology concept views for the Italian REC community domain."""
        _ctx = {"community_key": "community_key"}
        return [
            OntologySpec(
                id="rec_energy",
                description="REC self-consumption observations as SOSA observations",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="rec_self_consumption",
                        mapper_spec_path=SPECS_DIR / "obs_rec_energy.yaml",
                        context_vars=_ctx,
                    )
                ],
            ),
            OntologySpec(
                id="pv_forecast",
                description="PV potential forecast as PECO forecasts",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="pv_potential_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_pv_forecast.yaml",
                        context_vars=_ctx,
                    )
                ],
            ),
            OntologySpec(
                id="rec_forecast",
                description="REC energy forecast as PECO forecasts",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="rec_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_rec_forecast.yaml",
                        context_vars=_ctx,
                    )
                ],
            ),
            OntologySpec(
                id="community_snapshot",
                description="Full community view: self-consumption + REC forecast + PV forecast",
                bindings=[
                    OntologyFetcherBinding(
                        fetcher_id="rec_self_consumption",
                        mapper_spec_path=SPECS_DIR / "obs_rec_energy.yaml",
                        context_vars=_ctx,
                    ),
                    OntologyFetcherBinding(
                        fetcher_id="rec_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_rec_forecast.yaml",
                        context_vars=_ctx,
                    ),
                    OntologyFetcherBinding(
                        fetcher_id="pv_potential_forecast",
                        mapper_spec_path=SPECS_DIR / "obs_pv_forecast.yaml",
                        context_vars=_ctx,
                    ),
                ],
            ),
        ]


# Module-level instance for import by the domain loader
domain = ITEnergyCommunityDomain()
