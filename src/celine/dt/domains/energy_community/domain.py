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
                    FROM ds_dev_gold.rec_virtual_consumption
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
        ]
        return base + italian_specific


# Module-level instance for import by the domain loader
domain = ITEnergyCommunityDomain()
