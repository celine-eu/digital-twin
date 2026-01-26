# celine/dt/modules/rec_planning/module.py
"""
REC Planning module registration.

Registers the REC Planning simulation with the DT registry.
"""
from __future__ import annotations

from celine.dt.modules.rec_planning.simulation import RECPlanningSimulation


class RECPlanningModule:
    """
    REC Planning module.

    Provides simulations for planning PV and storage installations
    in Renewable Energy Communities.
    """

    name = "rec-planning"
    version = "1.0.0"

    def register(self, registry) -> None:
        """
        Register simulations with the registry.

        Args:
            registry: DTRegistry or object with 'simulations' attribute
        """
        # Get simulation registry
        if hasattr(registry, "simulations"):
            simulation_registry = registry.simulations
        else:
            # Assume it's already a simulation registry
            simulation_registry = registry

        simulation_registry.register(RECPlanningSimulation())


# Module instance for import
module = RECPlanningModule()
