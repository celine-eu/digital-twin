from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celine.dt.core.dt import DT
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import MemoryStateStore
from celine.dt.core.values.config import ValueFetcherSpec
from celine.dt.core.values.executor import ValuesFetcher
from celine.dt.core.values.registry import FetcherDescriptor, ValuesRegistry
from celine.dt.core.values.service import ValuesService
from celine.dt.modules.ev_charging.module import module


class FakeSqlClient:
    """SQL-only fake client.

    Returns deterministic rows based on query intent.
    """

    async def query(self, *, sql: str, limit: int = 1000, offset: int = 0):
        sql = sql.lower()

        if "dwd_icon_d2_solar_energy" in sql:
            return [
                {"solar_energy_kwh_per_m2": 1.5},
                {"solar_energy_kwh_per_m2": 3.0},
                {"solar_energy_kwh_per_m2": 4.2},
            ]

        if "folgaria_weather_hourly" in sql:
            return [
                {"clouds": 20},
                {"clouds": 30},
                {"clouds": 25},
                {"clouds": 35},
            ]

        return []


def test_ev_charging_readiness_end_to_end():
    registry = DTRegistry()
    module.register(registry)

    runner = DTAppRunner()

    values_registry = ValuesRegistry()
    fake_client = FakeSqlClient()

    values_registry.register(
        FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="ev-charging.dwd_solar_energy",
                client="dataset_api",
                query="SELECT * FROM datasets.ds_dev_gold.dwd_icon_d2_solar_energy WHERE run_time_utc <= :start",
                payload_schema={
                    "type": "object",
                    "required": ["start"],
                    "properties": {"start": {"type": "string"}},
                },
                limit=5000,
            ),
            client=fake_client,
        )
    )

    values_registry.register(
        FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="ev-charging.weather_hourly_by_location",
                client="dataset_api",
                query="SELECT * FROM datasets.ds_dev_gold.folgaria_weather_hourly WHERE ts >= :start AND ts < :end AND location_id = :location_id",
                payload_schema={
                    "type": "object",
                    "required": ["start", "end", "location_id"],
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "location_id": {"type": "string"},
                    },
                },
                limit=10000,
            ),
            client=fake_client,
        )
    )

    values_registry.register(
        FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="ev-charging.weather_hourly_by_bbox",
                client="dataset_api",
                query="SELECT * FROM datasets.ds_dev_gold.folgaria_weather_hourly WHERE ts >= :start AND ts < :end AND lat BETWEEN :lat_min AND :lat_max AND lon BETWEEN :lon_min AND :lon_max",
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
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "lat_min": {"type": "number"},
                        "lat_max": {"type": "number"},
                        "lon_min": {"type": "number"},
                        "lon_max": {"type": "number"},
                    },
                },
                limit=10000,
            ),
            client=fake_client,
        )
    )

    dt = DT(
        registry=registry,
        runner=runner,
        values=ValuesService(registry=values_registry, fetcher=ValuesFetcher()),
        state=MemoryStateStore(),
        token_provider=None,
        services={},
    )

    context = dt.create_context(request=None, request_scope={})

    payload = {
        "community_id": "rec-folgaria",
        "location": {"lat": 45.91, "lon": 11.17},
        "window_hours": 24,
        "pv_capacity_kw": 1000,
        "ev_charging_capacity_kw": 600,
        "weather_location_id": "folgaria",
        "start_utc": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
    }

    result = asyncio.run(
        runner.run(
            registry=registry,
            app_key="ev-charging-readiness",
            payload=payload,
            context=context,
        )
    )

    assert result["@type"] == "EVChargingReadiness"
    assert result["communityId"] == "rec-folgaria"
    assert result["expectedPVKWh"] > 0
    assert result["evChargingCapacityKWh"] == 600 * 24

    assert result["chargingIndicator"] in {
        "OPTIMAL",
        "MARGINAL",
        "SUBOPTIMAL",
        "UNSTABLE",
    }

    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["drivers"], list)
    assert isinstance(result["recommendations"], list)
