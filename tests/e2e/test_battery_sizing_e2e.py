import asyncio

from celine.dt.core.runner import DTAppRunner
from celine.dt.core.registry import DTRegistry
from celine.dt.core.context import RunContext
from celine.dt.modules.battery_sizing.module import module
from celine.dt.contracts.state import AppStatus
from tests.conftest import FakeDatasetClient


def test_battery_sizing_end_to_end():
    registry = DTRegistry()
    module.register(registry)

    runner = DTAppRunner()

    context = RunContext.create(
        datasets=FakeDatasetClient(),
        state=None,  # not used by app
        token_provider=None,  # not used
    )

    payload = {
        "demand": {"values": [5, 5, 5, 5], "timestep_hours": 1},
        "pv": {"values": [0, 10, 10, 0], "timestep_hours": 1},
        "max_capacity_kwh": 20,
    }

    result = asyncio.run(
        runner.run(
            registry=registry,
            app_key="battery-sizing",
            payload=payload,
            context=context,
        )
    )

    # Domain-level assertions
    print(result)
    assert result["capacityKWh"] == 20
    assert result["gridImportKWh"] >= 0
    assert 0.0 <= result["selfConsumptionRatio"] <= 1.0
