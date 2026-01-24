# tests/core/clients/test_loader.py
from __future__ import annotations

import pytest

from celine.dt.core.clients.config import ClientsConfig, ClientSpec
from celine.dt.core.clients.loader import load_and_register_clients


# Test client class that we can import
class DummyClient:
    def __init__(self, base_url: str, timeout: float = 10.0, token_provider=None):
        self.base_url = base_url
        self.timeout = timeout
        self.token_provider = token_provider


class TestLoadAndRegisterClients:
    def test_load_simple_client(self):
        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="dummy",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    config={"base_url": "http://example.com", "timeout": 30.0},
                )
            ]
        )

        registry = load_and_register_clients(cfg=cfg)

        assert "dummy" in registry
        client = registry.get("dummy")
        assert isinstance(client, DummyClient)
        assert client.base_url == "http://example.com"
        assert client.timeout == 30.0

    def test_load_client_with_injection(self):
        token_provider = object()  # dummy token provider

        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="auth_client",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    inject=["token_provider"],
                    config={"base_url": "http://example.com"},
                )
            ]
        )

        registry = load_and_register_clients(
            cfg=cfg,
            injectable_services={"token_provider": token_provider},
        )

        client = registry.get("auth_client")
        assert client.token_provider is token_provider

    def test_missing_injectable_service_raises(self):
        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="bad_client",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    inject=["nonexistent_service"],
                    config={"base_url": "http://example.com"},
                )
            ]
        )

        with pytest.raises(ValueError, match="requires injectable service"):
            load_and_register_clients(cfg=cfg, injectable_services={})

    def test_invalid_class_path_raises(self):
        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="bad_client",
                    class_path="nonexistent.module:Class",
                    config={},
                )
            ]
        )

        with pytest.raises(ImportError):
            load_and_register_clients(cfg=cfg)

    def test_instantiation_error_raises(self):
        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="bad_client",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    config={"invalid_kwarg": "value"},  # Missing required base_url
                )
            ]
        )

        with pytest.raises(TypeError, match="Failed to instantiate"):
            load_and_register_clients(cfg=cfg)

    def test_load_multiple_clients(self):
        cfg = ClientsConfig(
            clients=[
                ClientSpec(
                    name="client_a",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    config={"base_url": "http://a.com"},
                ),
                ClientSpec(
                    name="client_b",
                    class_path="tests.core.clients.test_loader:DummyClient",
                    config={"base_url": "http://b.com"},
                ),
            ]
        )

        registry = load_and_register_clients(cfg=cfg)

        assert len(registry) == 2
        assert registry.get("client_a").base_url == "http://a.com"
        assert registry.get("client_b").base_url == "http://b.com"

    def test_empty_config(self):
        cfg = ClientsConfig(clients=[])

        registry = load_and_register_clients(cfg=cfg)

        assert len(registry) == 0
