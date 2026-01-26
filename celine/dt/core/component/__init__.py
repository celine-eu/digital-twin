# celine/dt/core/component/registry.py
"""
Registry for Digital Twin components.

Components are registered by modules and made available for use
by Apps and Simulations through the RunContext.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from celine.dt.contracts.component import ComponentDescriptor, DTComponent

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """
    Registry for DTComponent instances.

    Components are registered during module initialization and
    accessed by Apps and Simulations via their key.

    Example:
        registry = ComponentRegistry()
        registry.register(EnergyBalanceComponent())

        # Later, in an App or Simulation:
        component = registry.get("energy-balance.calculator")
        result = await component.compute(input, context)
    """

    def __init__(self) -> None:
        self._components: dict[str, ComponentDescriptor] = {}

    def register(self, component: DTComponent) -> None:
        """
        Register a component.

        Args:
            component: Component instance to register

        Raises:
            ValueError: If a component with this key already exists
        """
        key = component.key

        if key in self._components:
            raise ValueError(f"Component '{key}' is already registered")

        self._components[key] = ComponentDescriptor(component=component)
        logger.info("Registered component: %s (v%s)", key, component.version)

    def get(self, key: str) -> DTComponent:
        """
        Get a component by key.

        Args:
            key: Component identifier (e.g., "energy-balance.calculator")

        Returns:
            The component instance

        Raises:
            KeyError: If component not found
        """
        if key not in self._components:
            available = ", ".join(self._components.keys()) or "(none)"
            raise KeyError(f"Component '{key}' not found. Available: {available}")

        return self._components[key].component

    def get_descriptor(self, key: str) -> ComponentDescriptor:
        """
        Get a component descriptor by key.

        Args:
            key: Component identifier

        Returns:
            The component descriptor with metadata

        Raises:
            KeyError: If component not found
        """
        if key not in self._components:
            raise KeyError(f"Component '{key}' not found")

        return self._components[key]

    def has(self, key: str) -> bool:
        """
        Check if a component is registered.

        Args:
            key: Component identifier

        Returns:
            True if component exists
        """
        return key in self._components

    def list(self) -> list[dict[str, Any]]:
        """
        List all registered components with metadata.

        Returns:
            List of component descriptions
        """
        return [desc.describe() for desc in self._components.values()]

    def keys(self) -> list[str]:
        """
        List all registered component keys.

        Returns:
            List of component keys
        """
        return list(self._components.keys())

    def items(self) -> Iterator[tuple[str, DTComponent]]:
        """
        Iterate over (key, component) pairs.

        Yields:
            Tuples of (key, component)
        """
        for key, desc in self._components.items():
            yield key, desc.component

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        return len(self._components)

    def __iter__(self) -> Iterator[str]:
        return iter(self._components)
