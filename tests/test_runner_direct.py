import asyncio
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.registry import DTRegistry
from celine.dt.core.context import RunContext
from celine.dt.modules.battery_sizing.module import module


def test_battery_sizing_direct():
    registry = DTRegistry()
    module.register(registry)

    runner = DTAppRunner()

    payload = {
        "demand": {"values": [5, 5, 5, 5], "timestep_hours": 1},
        "pv": {"values": [0, 10, 10, 0], "timestep_hours": 1},
    }

    result = asyncio.run(
        runner.run(
            registry=registry,
            app_key="battery-sizing",
            payload=payload,
            context=RunContext.create(
                datasets=None,
                state=None,
                token_provider=None,
            ),
        )
    )

    assert result["capacityKWh"] > 0
