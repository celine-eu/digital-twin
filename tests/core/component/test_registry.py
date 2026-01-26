# tests/core/component/test_registry.py
"""Tests for ComponentRegistry."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from celine.dt.core.component import ComponentRegistry
from celine.dt.contracts.component import ComponentDescriptor, DTComponent


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures: Minimal DTComponent implementation
# ──────────────────────────────────────────────────────────────────────────────


class DummyInput(BaseModel):
    value: float


class DummyOutput(BaseModel):
    result: float


class DummyComponent(DTComponent):
    """Minimal component for testing."""

    key = "test-component"
    version = "1.0.0"

    input_type = DummyInput
    output_type = DummyOutput

    async def compute(self, input: DummyInput, context) -> DummyOutput:
        return DummyOutput(result=input.value * 2)


class AnotherComponent(DTComponent):
    """Another component for testing multiple registrations."""

    key = "another-component"
    version = "2.0.0"

    input_type = DummyInput
    output_type = DummyOutput

    async def compute(self, input: DummyInput, context) -> DummyOutput:
        return DummyOutput(result=input.value + 10)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestComponentRegistry:
    """Tests for ComponentRegistry."""

    def test_register_component(self):
        """Test basic component registration."""
        registry = ComponentRegistry()
        component = DummyComponent()

        registry.register(component)

        assert registry.has("test-component")
        assert "test-component" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self):
        """Test that registering duplicate component raises ValueError."""
        registry = ComponentRegistry()
        component1 = DummyComponent()
        component2 = DummyComponent()

        registry.register(component1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(component2)

    def test_get_component(self):
        """Test retrieving a component by key."""
        registry = ComponentRegistry()
        component = DummyComponent()
        registry.register(component)

        retrieved = registry.get("test-component")

        assert retrieved is component

    def test_get_nonexistent_raises(self):
        """Test that getting nonexistent component raises KeyError."""
        registry = ComponentRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_get_descriptor(self):
        """Test retrieving component descriptor."""
        registry = ComponentRegistry()
        component = DummyComponent()
        registry.register(component)

        descriptor = registry.get_descriptor("test-component")

        assert isinstance(descriptor, ComponentDescriptor)
        assert descriptor.key == "test-component"
        assert descriptor.version == "1.0.0"

    def test_has_component(self):
        """Test checking if component exists."""
        registry = ComponentRegistry()

        assert not registry.has("test-component")

        registry.register(DummyComponent())

        assert registry.has("test-component")
        assert not registry.has("nonexistent")

    def test_list_components(self):
        """Test listing all registered components."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())
        registry.register(AnotherComponent())

        components = registry.list()

        assert len(components) == 2
        keys = {c["key"] for c in components}
        assert keys == {"test-component", "another-component"}

    def test_keys(self):
        """Test getting all component keys."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())
        registry.register(AnotherComponent())

        keys = registry.keys()

        assert set(keys) == {"test-component", "another-component"}

    def test_items_iteration(self):
        """Test iterating over (key, component) pairs."""
        registry = ComponentRegistry()
        component1 = DummyComponent()
        component2 = AnotherComponent()
        registry.register(component1)
        registry.register(component2)

        items = list(registry.items())

        assert len(items) == 2
        keys = {key for key, _ in items}
        assert keys == {"test-component", "another-component"}

    def test_len(self):
        """Test getting registry size."""
        registry = ComponentRegistry()

        assert len(registry) == 0

        registry.register(DummyComponent())
        assert len(registry) == 1

        registry.register(AnotherComponent())
        assert len(registry) == 2

    def test_iter(self):
        """Test iterating over keys."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())
        registry.register(AnotherComponent())

        keys = list(iter(registry))

        assert set(keys) == {"test-component", "another-component"}

    def test_contains(self):
        """Test 'in' operator."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())

        assert "test-component" in registry
        assert "nonexistent" not in registry


class TestComponentDescriptor:
    """Tests for ComponentDescriptor."""

    def test_describe(self):
        """Test describe() returns correct metadata."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())

        descriptor = registry.get_descriptor("test-component")
        description = descriptor.describe()

        assert description["key"] == "test-component"
        assert description["version"] == "1.0.0"
        assert "input_schema" in description
        assert "output_schema" in description

    def test_schema_properties(self):
        """Test schema properties return valid JSON Schemas."""
        registry = ComponentRegistry()
        registry.register(DummyComponent())

        descriptor = registry.get_descriptor("test-component")

        # Check input schema
        input_schema = descriptor.input_schema
        assert input_schema["type"] == "object"
        assert "value" in input_schema.get("properties", {})

        # Check output schema
        output_schema = descriptor.output_schema
        assert output_schema["type"] == "object"
        assert "result" in output_schema.get("properties", {})
