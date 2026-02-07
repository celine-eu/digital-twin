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
                id="gse_incentive_rates",
                client="dataset_api",
                query="""
                    SELECT valid_from, valid_to, rate_eur_kwh, zone
                    FROM gse_incentive_rates
                    WHERE zone = '{{ entity.metadata.gse_zone | default("CENTRO-NORD") }}'
                      AND valid_from <= :reference_date
                    ORDER BY valid_from DESC
                    LIMIT 1
                """,
                payload_schema={
                    "type": "object",
                    "required": ["reference_date"],
                    "properties": {
                        "reference_date": {"type": "string"},
                    },
                },
            ),
            ValueFetcherSpec(
                id="weather_forecast",
                client="dataset_api",
                query="""
                    SELECT interval_end_utc, solar_energy_kwh_per_m2
                    FROM dwd_icon_d2_solar_energy
                    WHERE interval_end_utc > :start
                      AND interval_end_utc <= :end
                      AND lat BETWEEN :lat_min AND :lat_max
                      AND lon BETWEEN :lon_min AND :lon_max
                    ORDER BY interval_end_utc
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "required": [
                        "start",
                        "end",
                        "lat_min",
                        "lat_max",
                        "lon_min",
                        "lon_max",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "lat_min": {"type": "number"},
                        "lat_max": {"type": "number"},
                        "lon_min": {"type": "number"},
                        "lon_max": {"type": "number"},
                    },
                },
            ),
        ]
        return base + italian_specific


# Module-level instance for import by the domain loader
domain = ITEnergyCommunityDomain()
