# celine/dt/core/clients/registry.py
"""
Clients registry – stores data client instances by name.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClientsRegistry:
    """Named registry for data client instances (dataset API, etc.)."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def register(self, name: str, client: Any) -> None:
        if name in self._clients:
            raise ValueError(f"Client '{name}' already registered")
        self._clients[name] = client
        logger.info("Registered client: %s (%s)", name, type(client).__name__)

    def get(self, name: str) -> Any:
        try:
            return self._clients[name]
        except KeyError:
            raise KeyError(f"Client '{name}' not found. Available: {list(self._clients)}")

    def has(self, name: str) -> bool:
        return name in self._clients

    def list(self) -> list[str]:
        return list(self._clients.keys())
