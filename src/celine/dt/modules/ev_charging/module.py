from __future__ import annotations

from celine.dt.core.registry import DTRegistry
from celine.dt.modules.ev_charging.app import EVChargingReadinessApp


class EVChargingIntelligenceModule:
    name = "ev-charging"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(EVChargingReadinessApp())


module = EVChargingIntelligenceModule()
