# celine/dt/core/values/registry.py
"""
Registry for value fetchers.
"""
from __future__ import annotations

import logging
from typing import Any

from celine.dt.core.values.config import ValueFetcherSpec

logger = logging.getLogger(__name__)


class FetcherDescriptor:
    """
    Descriptor containing fetcher spec and resolved dependencies.

    Attributes:
        spec: The fetcher specification
        client: Resolved client instance
        output_mapper: Resolved output mapper instance (or None)
    """

    def __init__(
        self,
        spec: ValueFetcherSpec,
        client: Any,
        output_mapper: Any | None = None,
    ) -> None:
        self.spec = spec
        self.client = client
        self.output_mapper = output_mapper

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def has_payload_schema(self) -> bool:
        return self.spec.payload_schema is not None


class ValuesRegistry:
    """
    Registry for value fetchers.

    Stores fetcher descriptors which include resolved client references
    and optional output mappers.
    """

    def __init__(self) -> None:
        self._fetchers: dict[str, FetcherDescriptor] = {}

    def register(self, descriptor: FetcherDescriptor) -> None:
        """
        Register a fetcher descriptor.

        Args:
            descriptor: Fetcher descriptor with resolved dependencies

        Raises:
            ValueError: If a fetcher with this ID is already registered
        """
        if descriptor.id in self._fetchers:
            raise ValueError(f"Fetcher '{descriptor.id}' is already registered")

        self._fetchers[descriptor.id] = descriptor
        logger.info("Registered fetcher: %s", descriptor.id)

    def get(self, fetcher_id: str) -> FetcherDescriptor:
        """
        Get a fetcher descriptor by ID.

        Args:
            fetcher_id: Fetcher identifier

        Returns:
            The fetcher descriptor

        Raises:
            KeyError: If no fetcher with this ID exists
        """
        if fetcher_id not in self._fetchers:
            raise KeyError(f"Fetcher '{fetcher_id}' not found")

        return self._fetchers[fetcher_id]

    def has(self, fetcher_id: str) -> bool:
        """
        Check if a fetcher is registered.

        Args:
            fetcher_id: Fetcher identifier

        Returns:
            True if fetcher exists, False otherwise
        """
        return fetcher_id in self._fetchers

    def list(self) -> list[dict[str, Any]]:
        """
        List all registered fetchers with metadata.

        Returns:
            List of dicts with id, client, has_payload_schema
        """
        return [
            {
                "id": desc.id,
                "client": desc.spec.client,
                "has_payload_schema": desc.has_payload_schema,
            }
            for desc in self._fetchers.values()
        ]

    def describe(self, fetcher_id: str) -> dict[str, Any]:
        """
        Get detailed description of a fetcher.

        Args:
            fetcher_id: Fetcher identifier

        Returns:
            Dict with fetcher metadata and payload schema

        Raises:
            KeyError: If fetcher not found
        """
        desc = self.get(fetcher_id)
        spec = desc.spec

        return {
            "id": spec.id,
            "client": spec.client,
            "query": spec.query,
            "limit": spec.limit,
            "offset": spec.offset,
            "payload_schema": spec.payload_schema,
            "has_output_mapper": desc.output_mapper is not None,
        }

    def __contains__(self, fetcher_id: str) -> bool:
        return self.has(fetcher_id)

    def __len__(self) -> int:
        return len(self._fetchers)
