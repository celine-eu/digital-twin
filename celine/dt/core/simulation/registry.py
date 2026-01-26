# celine/dt/core/simulation/registry.py
"""
Registry for Digital Twin simulations.

Simulations are registered by modules and accessed via the API.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from celine.dt.contracts.simulation import DTSimulation, SimulationDescriptor

logger = logging.getLogger(__name__)


class SimulationRegistry:
    """
    Registry for DTSimulation instances.

    Simulations are registered during module initialization and
    accessed via the /simulations API.

    Example:
        registry = SimulationRegistry()
        registry.register(RECPlanningSimulation())

        # Later, via API:
        simulation = registry.get("rec-planning")
    """

    def __init__(self) -> None:
        self._simulations: dict[str, SimulationDescriptor] = {}

    def register(self, simulation: DTSimulation) -> None:
        """
        Register a simulation.

        Args:
            simulation: Simulation instance to register

        Raises:
            ValueError: If a simulation with this key already exists
        """
        key = simulation.key

        if key in self._simulations:
            raise ValueError(f"Simulation '{key}' is already registered")

        self._simulations[key] = SimulationDescriptor(simulation=simulation)
        logger.info("Registered simulation: %s (v%s)", key, simulation.version)

    def get(self, key: str) -> DTSimulation:
        """
        Get a simulation by key.

        Args:
            key: Simulation identifier (e.g., "rec-planning")

        Returns:
            The simulation instance

        Raises:
            KeyError: If simulation not found
        """
        if key not in self._simulations:
            available = ", ".join(self._simulations.keys()) or "(none)"
            raise KeyError(f"Simulation '{key}' not found. Available: {available}")

        return self._simulations[key].simulation

    def get_descriptor(self, key: str) -> SimulationDescriptor:
        """
        Get a simulation descriptor by key.

        Args:
            key: Simulation identifier

        Returns:
            The simulation descriptor with metadata

        Raises:
            KeyError: If simulation not found
        """
        if key not in self._simulations:
            raise KeyError(f"Simulation '{key}' not found")

        return self._simulations[key]

    def has(self, key: str) -> bool:
        """
        Check if a simulation is registered.

        Args:
            key: Simulation identifier

        Returns:
            True if simulation exists
        """
        return key in self._simulations

    def list(self) -> list[dict[str, Any]]:
        """
        List all registered simulations with metadata.

        Returns:
            List of simulation descriptions
        """
        return [desc.describe() for desc in self._simulations.values()]

    def keys(self) -> list[str]:
        """
        List all registered simulation keys.

        Returns:
            List of simulation keys
        """
        return list(self._simulations.keys())

    def items(self) -> Iterator[tuple[str, DTSimulation]]:
        """
        Iterate over (key, simulation) pairs.

        Yields:
            Tuples of (key, simulation)
        """
        for key, desc in self._simulations.items():
            yield key, desc.simulation

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        return len(self._simulations)

    def __iter__(self) -> Iterator[str]:
        return iter(self._simulations)
