# celine/dt/core/simulation/registry.py
"""
Simulation registry for domain-scoped simulations.
"""
from __future__ import annotations

import logging
from typing import Any

from celine.dt.contracts.simulation import DTSimulation, SimulationDescriptor

logger = logging.getLogger(__name__)


class SimulationRegistry:
    """Named registry for simulation descriptors."""

    def __init__(self) -> None:
        self._simulations: dict[str, SimulationDescriptor] = {}

    def register(self, simulation: DTSimulation) -> None:  # type: ignore[type-arg]
        desc = SimulationDescriptor(simulation)
        if desc.key in self._simulations:
            raise ValueError(f"Simulation '{desc.key}' already registered")
        self._simulations[desc.key] = desc
        logger.info("Registered simulation: %s v%s", desc.key, desc.version)

    def get(self, key: str) -> SimulationDescriptor:
        try:
            return self._simulations[key]
        except KeyError:
            raise KeyError(
                f"Simulation '{key}' not found. Available: {list(self._simulations)}"
            )

    def has(self, key: str) -> bool:
        return key in self._simulations

    def list_all(self) -> list[dict[str, Any]]:
        return [d.describe() for d in self._simulations.values()]

    def __len__(self) -> int:
        return len(self._simulations)
