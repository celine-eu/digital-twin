# tests/core/test_registry.py
"""Tests for DTRegistry with apps, components, and simulations."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from celine.dt.core.registry import DTRegistry
from celine.dt.contracts.component import DTComponent
from celine.dt.contracts.simulation import DTSimulation


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────────────────────────


class DummyConfig(BaseModel):
    value: int


class DummyResult(BaseModel):
    result: int


class DummyApp:
    """Minimal app for testing."""

    key = "dummy-app"
    version = "1.0.0"

    config_type = DummyConfig
    result_type = DummyResult

    input_mapper = None
    output_mapper = None

    async def run(self, config, context):
        return DummyResult(result=config.value * 2)


class DummyInput(BaseModel):
    value: float


class DummyOutput(BaseModel):
    result: float


class DummyComponent(DTComponent):
    """Minimal component for testing."""

    key = "dummy-component"
    version = "1.0.0"

    input_type = DummyInput
    output_type = DummyOutput

    async def compute(self, input, context):
        return DummyOutput(result=input.value * 2)


class DummyScenarioConfig(BaseModel):
    community_id: str


class DummyScenario(BaseModel):
    community_id: str


class DummyParameters(BaseModel):
    add_pv_kwp: float = 0.0


class DummySimResult(BaseModel):
    ratio: float


class DummySimulation(DTSimulation):
    """Minimal simulation for testing."""

    key = "dummy-simulation"
    version = "1.0.0"

    scenario_config_type = DummyScenarioConfig
    scenario_type = DummyScenario
    parameters_type = DummyParameters
    result_type = DummySimResult

    async def build_scenario(self, config, workspace, context):
        return DummyScenario(community_id=config.community_id)

    async def simulate(self, scenario, parameters, context):
        return DummySimResult(ratio=0.8)

    def get_default_parameters(self):
        return DummyParameters()


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestDTRegistryApps:
    """Tests for DTRegistry app management."""

    def test_register_app(self):
        """Test basic app registration."""
        registry = DTRegistry()
        app = DummyApp()

        registry.register_app(app)

        assert registry.has_app("dummy-app")

    def test_register_app_with_module_name(self):
        """Test registering app with module tracking."""
        registry = DTRegistry()
        app = DummyApp()

        registry.register_app(app, module_name="test-module")

        assert registry.has_app("dummy-app")

    def test_register_app_with_defaults(self):
        """Test registering app with default values."""
        registry = DTRegistry()
        app = DummyApp()
        defaults = {"value": 42}

        registry.register_app(app, defaults=defaults)

        descriptor = registry.get_app_descriptor("dummy-app")
        assert descriptor.defaults == {"value": 42}

    def test_register_duplicate_app_raises(self):
        """Test that registering duplicate app raises ValueError."""
        registry = DTRegistry()
        registry.register_app(DummyApp())

        with pytest.raises(ValueError, match="already registered"):
            registry.register_app(DummyApp())

    def test_get_app(self):
        """Test retrieving an app."""
        registry = DTRegistry()
        app = DummyApp()
        registry.register_app(app)

        retrieved = registry.get_app("dummy-app")

        assert retrieved is app

    def test_get_app_not_found_raises(self):
        """Test that getting nonexistent app raises KeyError."""
        registry = DTRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.get_app("nonexistent")

    def test_list_apps(self):
        """Test listing registered apps."""
        registry = DTRegistry()
        registry.register_app(DummyApp())

        apps = registry.list_apps()

        assert len(apps) == 1
        assert apps[0]["key"] == "dummy-app"

    def test_describe_app(self):
        """Test describing an app."""
        registry = DTRegistry()
        registry.register_app(DummyApp())

        description = registry.describe_app("dummy-app")

        assert description["key"] == "dummy-app"
        assert description["version"] == "1.0.0"
        assert "config_schema" in description
        assert "result_schema" in description

    def test_app_keys(self):
        """Test getting app keys."""
        registry = DTRegistry()
        registry.register_app(DummyApp())

        keys = registry.app_keys()

        assert keys == ["dummy-app"]


class TestDTRegistryComponents:
    """Tests for DTRegistry component management."""

    def test_register_component(self):
        """Test component registration through DTRegistry."""
        registry = DTRegistry()
        component = DummyComponent()

        registry.register_component(component)

        assert registry.components.has("dummy-component")

    def test_get_component(self):
        """Test getting component through DTRegistry."""
        registry = DTRegistry()
        component = DummyComponent()
        registry.register_component(component)

        retrieved = registry.get_component("dummy-component")

        assert retrieved is component

    def test_components_property(self):
        """Test accessing component registry via property."""
        registry = DTRegistry()
        component = DummyComponent()
        registry.components.register(component)

        assert len(registry.components) == 1
        assert "dummy-component" in registry.components


class TestDTRegistrySimulations:
    """Tests for DTRegistry simulation management."""

    def test_register_simulation(self):
        """Test simulation registration through DTRegistry."""
        registry = DTRegistry()
        simulation = DummySimulation()

        registry.register_simulation(simulation)

        assert registry.simulations.has("dummy-simulation")

    def test_get_simulation(self):
        """Test getting simulation through DTRegistry."""
        registry = DTRegistry()
        simulation = DummySimulation()
        registry.register_simulation(simulation)

        retrieved = registry.get_simulation("dummy-simulation")

        assert retrieved is simulation

    def test_simulations_property(self):
        """Test accessing simulation registry via property."""
        registry = DTRegistry()
        simulation = DummySimulation()
        registry.simulations.register(simulation)

        assert len(registry.simulations) == 1
        assert "dummy-simulation" in registry.simulations


class TestDTRegistryModules:
    """Tests for DTRegistry module management."""

    def test_register_module(self):
        """Test module registration."""
        registry = DTRegistry()

        registry.register_module("test-module", "1.0.0")

        modules = registry.list_modules()
        assert modules["test-module"] == "1.0.0"

    def test_list_modules(self):
        """Test listing modules."""
        registry = DTRegistry()
        registry.register_module("module-a", "1.0.0")
        registry.register_module("module-b", "2.0.0")

        modules = registry.list_modules()

        assert len(modules) == 2
        assert modules["module-a"] == "1.0.0"
        assert modules["module-b"] == "2.0.0"


class TestDTRegistryOntology:
    """Tests for DTRegistry ontology management."""

    def test_active_ontology_default(self):
        """Test default active ontology is None."""
        registry = DTRegistry()

        assert registry.active_ontology is None

    def test_set_active_ontology(self):
        """Test setting active ontology."""
        registry = DTRegistry()

        registry.active_ontology = "celine"

        assert registry.active_ontology == "celine"

    def test_set_active_ontology_method(self):
        """Test set_active_ontology method."""
        registry = DTRegistry()

        registry.set_active_ontology("custom")

        assert registry.active_ontology == "custom"


class TestDTRegistrySummary:
    """Tests for DTRegistry summary."""

    def test_summary(self):
        """Test summary method."""
        registry = DTRegistry()
        registry.register_app(DummyApp())
        registry.register_component(DummyComponent())
        registry.register_simulation(DummySimulation())
        registry.active_ontology = "celine"

        summary = registry.summary()

        assert summary["apps"]["count"] == 1
        assert summary["apps"]["keys"] == ["dummy-app"]
        assert summary["components"]["count"] == 1
        assert summary["simulations"]["count"] == 1
        assert summary["active_ontology"] == "celine"

    def test_repr(self):
        """Test string representation."""
        registry = DTRegistry()
        registry.register_app(DummyApp())
        registry.register_component(DummyComponent())
        registry.register_simulation(DummySimulation())

        repr_str = repr(registry)

        assert "apps=1" in repr_str
        assert "components=1" in repr_str
        assert "simulations=1" in repr_str


class TestDTRegistryIntegration:
    """Integration tests for DTRegistry with all artifact types."""

    def test_full_registry_workflow(self):
        """Test registering apps, components, and simulations together."""
        registry = DTRegistry()

        # Register everything
        registry.register_app(DummyApp())
        registry.register_component(DummyComponent())
        registry.register_simulation(DummySimulation())
        registry.register_module("test-module", "1.0.0")
        registry.set_active_ontology("celine")

        # Verify all are accessible
        assert registry.has_app("dummy-app")
        assert registry.components.has("dummy-component")
        assert registry.simulations.has("dummy-simulation")
        assert "test-module" in registry.list_modules()
        assert registry.active_ontology == "celine"

        # Verify summary
        summary = registry.summary()
        assert summary["apps"]["count"] == 1
        assert summary["components"]["count"] == 1
        assert summary["simulations"]["count"] == 1
