# tests/core/simulation/test_registry.py
"""Tests for SimulationRegistry."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.contracts.simulation import DTSimulation, SimulationDescriptor


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures: Minimal DTSimulation implementation
# ──────────────────────────────────────────────────────────────────────────────


class DummyScenarioConfig(BaseModel):
    community_id: str


class DummyScenario(BaseModel):
    community_id: str
    total_kwh: float = 1000.0


class DummyParameters(BaseModel):
    add_pv_kwp: float = 0.0


class DummyResult(BaseModel):
    self_consumption_ratio: float


class DummySimulation(DTSimulation):
    """Minimal simulation for testing."""

    key = "test-simulation"
    version = "1.0.0"

    scenario_config_type = DummyScenarioConfig
    scenario_type = DummyScenario
    parameters_type = DummyParameters
    result_type = DummyResult

    async def build_scenario(self, config, workspace, context):
        return DummyScenario(community_id=config.community_id)

    async def simulate(self, scenario, parameters, context):
        return DummyResult(self_consumption_ratio=0.7)

    def get_default_parameters(self):
        return DummyParameters()


class AnotherSimulation(DTSimulation):
    """Another simulation for testing multiple registrations."""

    key = "another-simulation"
    version = "2.0.0"

    scenario_config_type = DummyScenarioConfig
    scenario_type = DummyScenario
    parameters_type = DummyParameters
    result_type = DummyResult

    async def build_scenario(self, config, workspace, context):
        return DummyScenario(community_id=config.community_id)

    async def simulate(self, scenario, parameters, context):
        return DummyResult(self_consumption_ratio=0.8)

    def get_default_parameters(self):
        return DummyParameters()


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSimulationRegistry:
    """Tests for SimulationRegistry."""

    def test_register_simulation(self):
        """Test basic simulation registration."""
        registry = SimulationRegistry()
        simulation = DummySimulation()

        registry.register(simulation)

        assert registry.has("test-simulation")
        assert "test-simulation" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self):
        """Test that registering duplicate simulation raises ValueError."""
        registry = SimulationRegistry()
        simulation1 = DummySimulation()
        simulation2 = DummySimulation()

        registry.register(simulation1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(simulation2)

    def test_get_simulation(self):
        """Test retrieving a simulation by key."""
        registry = SimulationRegistry()
        simulation = DummySimulation()
        registry.register(simulation)

        retrieved = registry.get("test-simulation")

        assert retrieved is simulation

    def test_get_nonexistent_raises(self):
        """Test that getting nonexistent simulation raises KeyError."""
        registry = SimulationRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_get_descriptor(self):
        """Test retrieving simulation descriptor."""
        registry = SimulationRegistry()
        simulation = DummySimulation()
        registry.register(simulation)

        descriptor = registry.get_descriptor("test-simulation")

        assert isinstance(descriptor, SimulationDescriptor)
        assert descriptor.key == "test-simulation"
        assert descriptor.version == "1.0.0"

    def test_has_simulation(self):
        """Test checking if simulation exists."""
        registry = SimulationRegistry()

        assert not registry.has("test-simulation")

        registry.register(DummySimulation())

        assert registry.has("test-simulation")
        assert not registry.has("nonexistent")

    def test_list_simulations(self):
        """Test listing all registered simulations."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())
        registry.register(AnotherSimulation())

        simulations = registry.list()

        assert len(simulations) == 2
        keys = {s["key"] for s in simulations}
        assert keys == {"test-simulation", "another-simulation"}

    def test_keys(self):
        """Test getting all simulation keys."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())
        registry.register(AnotherSimulation())

        keys = registry.keys()

        assert set(keys) == {"test-simulation", "another-simulation"}

    def test_items_iteration(self):
        """Test iterating over (key, simulation) pairs."""
        registry = SimulationRegistry()
        simulation1 = DummySimulation()
        simulation2 = AnotherSimulation()
        registry.register(simulation1)
        registry.register(simulation2)

        items = list(registry.items())

        assert len(items) == 2
        keys = {key for key, _ in items}
        assert keys == {"test-simulation", "another-simulation"}

    def test_len(self):
        """Test getting registry size."""
        registry = SimulationRegistry()

        assert len(registry) == 0

        registry.register(DummySimulation())
        assert len(registry) == 1

        registry.register(AnotherSimulation())
        assert len(registry) == 2

    def test_iter(self):
        """Test iterating over keys."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())
        registry.register(AnotherSimulation())

        keys = list(iter(registry))

        assert set(keys) == {"test-simulation", "another-simulation"}

    def test_contains(self):
        """Test 'in' operator."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())

        assert "test-simulation" in registry
        assert "nonexistent" not in registry


class TestSimulationDescriptor:
    """Tests for SimulationDescriptor."""

    def test_describe(self):
        """Test describe() returns correct metadata."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())

        descriptor = registry.get_descriptor("test-simulation")
        description = descriptor.describe()

        assert description["key"] == "test-simulation"
        assert description["version"] == "1.0.0"
        assert "scenario_config_schema" in description
        assert "parameters_schema" in description
        assert "result_schema" in description

    def test_schema_properties(self):
        """Test schema properties return valid JSON Schemas."""
        registry = SimulationRegistry()
        registry.register(DummySimulation())

        descriptor = registry.get_descriptor("test-simulation")

        # Check scenario config schema
        config_schema = descriptor.scenario_config_schema
        assert config_schema["type"] == "object"
        assert "community_id" in config_schema.get("properties", {})

        # Check parameters schema
        params_schema = descriptor.parameters_schema
        assert params_schema["type"] == "object"
        assert "add_pv_kwp" in params_schema.get("properties", {})

        # Check result schema
        result_schema = descriptor.result_schema
        assert result_schema["type"] == "object"
        assert "self_consumption_ratio" in result_schema.get("properties", {})
