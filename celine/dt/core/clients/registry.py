# celine/dt/core/clients/registry.py
"""
Registry for data clients.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class ClientsRegistry:
    """
    Registry for data clients.

    Provides named access to client instances for use by values fetchers
    and other components.
    """

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def register(self, name: str, client: Any) -> None:
        """
        Register a client instance.

        Args:
            name: Unique identifier for the client
            client: Client instance (typically implements DatasetClient protocol)

        Raises:
            ValueError: If a client with this name is already registered
        """
        if name in self._clients:
            raise ValueError(f"Client '{name}' is already registered")

        self._clients[name] = client
        logger.info("Registered client: %s", name)

    def get(self, name: str) -> Any:
        """
        Get a client by name.

        Args:
            name: Client identifier

        Returns:
            The registered client instance

        Raises:
            KeyError: If no client with this name exists
        """
        if name not in self._clients:
            raise KeyError(f"Client '{name}' not found in registry")

        return self._clients[name]

    def has(self, name: str) -> bool:
        """
        Check if a client is registered.

        Args:
            name: Client identifier

        Returns:
            True if client exists, False otherwise
        """
        return name in self._clients

    def list(self) -> list[str]:
        """
        List all registered client names.

        Returns:
            List of client identifiers
        """
        return list(self._clients.keys())

    def items(self) -> Iterator[tuple[str, Any]]:
        """
        Iterate over (name, client) pairs.

        Yields:
            Tuples of (client_name, client_instance)
        """
        yield from self._clients.items()

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        return len(self._clients)
