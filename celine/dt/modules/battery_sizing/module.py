from __future__ import annotations
from celine.dt.contracts.module import DTModule
from celine.dt.core.registry import DTRegistry
from celine.dt.modules.battery_sizing.app import BatterySizingApp

class BatterySizingModule:
    name = "battery-sizing"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(BatterySizingApp())

module: DTModule = BatterySizingModule()
