from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celine.dt.core.auth.provider import TokenProvider
from celine.dt.core.context import RunContext
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import MemoryStateStore
from celine.dt.modules.ev_charging.module import module
from celine.dt.core.datasets.client import DatasetClient


class FakeSqlDatasetClient(DatasetClient):
    """
    SQL-only fake dataset client.

    Returns deterministic rows based on query intent.
    """

    async def query(self, *, sql: str, limit: int = 1000, offset: int = 0):
        sql = sql.lower()

        # DWD solar cumulative forecast
        if "dwd_icon_d2_solar_energy" in sql:
            return [
                {"solar_energy_kwh_per_m2": 1.5},
                {"solar_energy_kwh_per_m2": 3.0},
                {"solar_energy_kwh_per_m2": 4.2},  # max → used as total
            ]

        # Hourly weather (cloudiness)
        if "folgaria_weather_hourly" in sql:
            return [
                {"clouds": 20},
                {"clouds": 30},
                {"clouds": 25},
                {"clouds": 35},
            ]

        return []

    def stream(self, *, sql: str, page_size: int = 1000):
        async def gen():
            yield await self.query(sql=sql)

        return gen()


def test_ev_charging_readiness_end_to_end():
    # --- registry + module ----------------------------------------------------
    registry = DTRegistry()
    module.register(registry)

    runner = DTAppRunner()

    # --- context --------------------------------------------------------------
    context = RunContext.create(
        datasets=FakeSqlDatasetClient(),
        state=MemoryStateStore(),
        token_provider=None,  # type: ignore
    )

    payload = {
        "community_id": "rec-folgaria",
        "location": {"lat": 45.91, "lon": 11.17},
        "window_hours": 24,
        "pv_capacity_kw": 1000,
        "ev_charging_capacity_kw": 600,
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

    # --- semantic assertions --------------------------------------------------
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

    # explainability must always be present
    assert isinstance(result["drivers"], list)
    assert isinstance(result["recommendations"], list)
