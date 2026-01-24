# tests/core/clients/test_registry.py
from __future__ import annotations

import pytest

from celine.dt.core.clients.registry import ClientsRegistry


class TestClientsRegistry:
    def test_register_and_get(self):
        registry = ClientsRegistry()
        client = object()  # dummy client

        registry.register("my_client", client)
        
        assert registry.get("my_client") is client

    def test_register_duplicate_raises(self):
        registry = ClientsRegistry()
        client = object()

        registry.register("my_client", client)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register("my_client", object())

    def test_get_nonexistent_raises(self):
        registry = ClientsRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_has(self):
        registry = ClientsRegistry()
        registry.register("existing", object())

        assert registry.has("existing") is True
        assert registry.has("nonexistent") is False

    def test_contains(self):
        registry = ClientsRegistry()
        registry.register("existing", object())

        assert "existing" in registry
        assert "nonexistent" not in registry

    def test_list(self):
        registry = ClientsRegistry()
        registry.register("client_a", object())
        registry.register("client_b", object())

        names = registry.list()
        
        assert set(names) == {"client_a", "client_b"}

    def test_items(self):
        registry = ClientsRegistry()
        client_a = object()
        client_b = object()
        registry.register("a", client_a)
        registry.register("b", client_b)

        items = dict(registry.items())
        
        assert items["a"] is client_a
        assert items["b"] is client_b

    def test_len(self):
        registry = ClientsRegistry()
        assert len(registry) == 0

        registry.register("a", object())
        assert len(registry) == 1

        registry.register("b", object())
        assert len(registry) == 2
