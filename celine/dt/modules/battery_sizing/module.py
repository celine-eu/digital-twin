from celine.dt.core.registry import DTRegistry
from celine.dt.modules.battery_sizing.app import BatterySizingApp
from celine.dt.modules.battery_sizing.mappers import (
    BatterySizingInputMapper,
    BatterySizingOutputMapper,
)


class BatterySizingModule:
    name = "battery-sizing"
    version = "2.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(
            BatterySizingApp(),
            input_mapper=BatterySizingInputMapper(),
            output_mapper=BatterySizingOutputMapper(),
        )


module = BatterySizingModule()
