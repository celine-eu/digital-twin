# celine/dt/core/values/service.py
"""
ValuesService – single entry-point for data retrieval.

Wraps registry look-up, entity context injection, and fetch execution.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.executor import FetchResult, FetcherDescriptor, ValuesFetcher

logger = logging.getLogger(__name__)


class ValuesRegistry:
    """In-memory registry for resolved fetcher descriptors."""

    def __init__(self) -> None:
        self._fetchers: dict[str, FetcherDescriptor] = {}

    def register(self, descriptor: FetcherDescriptor) -> None:
        if descriptor.id in self._fetchers:
            raise ValueError(f"Fetcher '{descriptor.id}' already registered")
        self._fetchers[descriptor.id] = descriptor
        logger.info("Registered value fetcher: %s", descriptor.id)

    def get(self, fetcher_id: str) -> FetcherDescriptor:
        try:
            return self._fetchers[fetcher_id]
        except KeyError:
            raise KeyError(
                f"Fetcher '{fetcher_id}' not found. Available: {list(self._fetchers)}"
            )

    def has(self, fetcher_id: str) -> bool:
        return fetcher_id in self._fetchers

    def list_all(self) -> list[dict[str, Any]]:
        return [
            {
                "id": d.id,
                "client": d.spec.client,
                "has_payload_schema": d.spec.payload_schema is not None,
            }
            for d in self._fetchers.values()
        ]

    def describe(self, fetcher_id: str) -> dict[str, Any]:
        d = self.get(fetcher_id)
        return {
            "id": d.spec.id,
            "client": d.spec.client,
            "query": d.spec.query,
            "limit": d.spec.limit,
            "offset": d.spec.offset,
            "payload_schema": d.spec.payload_schema,
            "has_output_mapper": d.output_mapper is not None,
        }

    def __len__(self) -> int:
        return len(self._fetchers)


class ValuesService:
    """Facade for the entire values subsystem."""

    def __init__(self, *, registry: ValuesRegistry, fetcher: ValuesFetcher) -> None:
        self._registry = registry
        self._fetcher = fetcher

    @property
    def registry(self) -> ValuesRegistry:
        return self._registry

    def list(self) -> list[dict[str, Any]]:
        return self._registry.list_all()

    def describe(self, fetcher_id: str) -> dict[str, Any]:
        return self._registry.describe(fetcher_id)

    def get_descriptor(self, fetcher_id: str) -> FetcherDescriptor:
        return self._registry.get(fetcher_id)

    async def fetch(
        self,
        *,
        fetcher_id: str,
        payload: Mapping[str, Any],
        limit: int | None = None,
        offset: int | None = None,
        entity: EntityInfo | None = None,
    ) -> FetchResult:
        descriptor = self._registry.get(fetcher_id)
        logger.debug("Values fetch: id=%s entity=%s", fetcher_id, entity.id if entity else None)
        return await self._fetcher.fetch(
            descriptor=descriptor,
            payload=dict(payload),
            entity=entity,
            limit=limit,
            offset=offset,
        )
