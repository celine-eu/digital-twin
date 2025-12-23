from __future__ import annotations

from celine.dt.contracts.module import DTModule
from celine.dt.core.registry import DTRegistry
from celine.dt.modules.battery_sizing.app import BatterySizingApp
from celine.dt.modules.battery_sizing.mappers import (
    BatterySizingInputMapper,
    BatterySizingOutputMapper,
)


class BatterySizingModule:
    name = "battery-sizing"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        app = BatterySizingApp()
        registry.register_app(app)
        registry.register_input_mapper(app.key, BatterySizingInputMapper())
        registry.register_output_mapper(app.key, BatterySizingOutputMapper())


module: DTModule = BatterySizingModule()
