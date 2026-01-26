# celine/dt/core/registry.py
"""
Main Digital Twin registry.

Integrates registries for:
- Apps (existing functionality)
- Components (new)
- Simulations (new)

This is the central registry that modules register their artifacts with.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Mapping

from celine.dt.core.component import ComponentRegistry
from celine.dt.core.simulation.registry import SimulationRegistry

logger = logging.getLogger(__name__)


class DTRegistry:
    """
    Central registry for Digital Twin artifacts.

    Manages registration and lookup of:
    - Apps: External-facing operations exposed via /apps API
    - Components: Internal computation building blocks
    - Simulations: What-if exploration exposed via /simulations API

    Example:
        registry = DTRegistry()

        # Modules register their artifacts
        registry.register_app(MyApp())
        registry.components.register(MyComponent())
        registry.simulations.register(MySimulation())

        # Later, retrieve them
        app = registry.get_app("my-app")
        component = registry.components.get("my-component")
        simulation = registry.simulations.get("my-simulation")
    """

    def __init__(self) -> None:
        # App registry (existing pattern from original code)
        self._apps: dict[str, Any] = {}  # AppDescriptor
        self._modules: dict[str, str] = {}

        # Component registry (new)
        self._components = ComponentRegistry()

        # Simulation registry (new)
        self._simulations = SimulationRegistry()

        # Active ontology (from original code)
        self._active_ontology: Optional[str] = None

        logger.info("DTRegistry initialized")

    # ─────────────────────────────────────────────────────────────────────────
    # Component Registry Access
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def components(self) -> ComponentRegistry:
        """Access the component registry."""
        return self._components

    def register_component(self, component: Any) -> None:
        """
        Convenience method to register a component.

        Args:
            component: DTComponent instance
        """
        self._components.register(component)

    def get_component(self, key: str) -> Any:
        """
        Convenience method to get a component.

        Args:
            key: Component identifier

        Returns:
            DTComponent instance
        """
        return self._components.get(key)

    # ─────────────────────────────────────────────────────────────────────────
    # Simulation Registry Access
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def simulations(self) -> SimulationRegistry:
        """Access the simulation registry."""
        return self._simulations

    def register_simulation(self, simulation: Any) -> None:
        """
        Convenience method to register a simulation.

        Args:
            simulation: DTSimulation instance
        """
        self._simulations.register(simulation)

    def get_simulation(self, key: str) -> Any:
        """
        Convenience method to get a simulation.

        Args:
            key: Simulation identifier

        Returns:
            DTSimulation instance
        """
        return self._simulations.get(key)

    # ─────────────────────────────────────────────────────────────────────────
    # App Registry (existing pattern from original code)
    # ─────────────────────────────────────────────────────────────────────────

    def register_app(
        self,
        app: Any,
        module_name: str | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Register an app.

        Args:
            app: DTApp instance
            module_name: Optional module name for tracking
        """
        from celine.dt.contracts.app import AppDescriptor

        key = app.key
        if key in self._apps:
            raise ValueError(f"App '{key}' is already registered")

        self._apps[key] = AppDescriptor(app=app, defaults=defaults or {})

        if module_name:
            self._modules[key] = module_name

        logger.info("Registered app: %s (v%s)", key, app.version)

    def get_app(self, key: str) -> Any:
        """
        Get an app by key.

        Args:
            key: App identifier

        Returns:
            DTApp instance
        """
        if key not in self._apps:
            available = ", ".join(self._apps.keys()) or "(none)"
            raise KeyError(f"App '{key}' not found. Available: {available}")

        return self._apps[key].app

    def get_app_descriptor(self, key: str) -> Any:
        """Get app descriptor with metadata."""
        if key not in self._apps:
            raise KeyError(f"App '{key}' not found")
        return self._apps[key]

    @property
    def apps(self) -> dict[str, Any]:
        """Direct access to the registered app descriptors (internal)."""
        return self._apps

    def describe_app(self, key: str) -> dict[str, Any]:
        """Describe a registered app (metadata + schemas)."""
        return self.get_app_descriptor(key).describe()

    def has_app(self, key: str) -> bool:
        """Check if app exists."""
        return key in self._apps

    def list_apps(self) -> list[dict[str, Any]]:
        """List all registered apps."""
        return [desc.describe() for desc in self._apps.values()]

    def app_keys(self) -> list[str]:
        """List all app keys."""
        return list(self._apps.keys())

    # ─────────────────────────────────────────────────────────────────────────
    # Ontology (from original code)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def active_ontology(self) -> Optional[str]:
        """Get the active ontology."""
        return self._active_ontology

    @active_ontology.setter
    def active_ontology(self, value: Optional[str]) -> None:
        """Set the active ontology."""
        self._active_ontology = value
        logger.info("Active ontology set to: %s", value)

    # ─────────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """
        Get a summary of registered artifacts.

        Returns:
            Dictionary with counts and lists
        """
        return {
            "apps": {
                "count": len(self._apps),
                "keys": self.app_keys(),
            },
            "components": {
                "count": len(self._components),
                "keys": self._components.keys(),
            },
            "simulations": {
                "count": len(self._simulations),
                "keys": self._simulations.keys(),
            },
            "active_ontology": self._active_ontology,
        }

    def __repr__(self) -> str:
        return (
            f"DTRegistry("
            f"apps={len(self._apps)}, "
            f"components={len(self._components)}, "
            f"simulations={len(self._simulations)})"
        )

    # ---------------------------------------------------------------------
    # Module + ontology helpers (used by module loader and CLI / APIs)
    # ---------------------------------------------------------------------

    def register_module(self, name: str, version: str) -> None:
        """Register a DT module (name -> version).

        Modules are higher-level bundles that register apps/components/simulations.
        Keeping them tracked enables diagnostics and compatibility checks.
        """
        self._modules[str(name)] = str(version)

    def list_modules(self) -> dict[str, str]:
        """Return registered modules (name -> version)."""
        return dict(self._modules)

    def set_active_ontology(self, value: str | None) -> None:
        """Convenience wrapper used by loaders/config to set active ontology."""
        self.active_ontology = value
