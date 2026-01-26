# celine/dt/modules/energy_balance/module.py
"""
Energy Balance module registration.

Registers energy balance components with the DT registry.
"""
from __future__ import annotations

from celine.dt.modules.energy_balance.components import (
    EnergyBalanceComponent,
    AggregatedBalanceComponent,
)


class EnergyBalanceModule:
    """
    Energy Balance module.

    Provides components for calculating energy balance metrics
    including self-consumption and self-sufficiency ratios.
    """

    name = "energy-balance"
    version = "1.0.0"

    def register(self, registry) -> None:
        """Register components with the DT registry."""

        # Register components
        if hasattr(registry, "components"):
            registry.components.register(EnergyBalanceComponent())
            registry.components.register(AggregatedBalanceComponent())


# Module instance for import
module = EnergyBalanceModule()
