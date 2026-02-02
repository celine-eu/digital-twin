# celine/dt/core/clients/__init__.py
"""Clients registry and loading infrastructure."""

from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.clients.loader import load_and_register_clients
from celine.dt.core.clients.config import load_clients_config, ClientSpec, ClientsConfig

__all__ = [
    "ClientsRegistry",
    "load_and_register_clients",
    "load_clients_config",
    "ClientSpec",
    "ClientsConfig",
]
