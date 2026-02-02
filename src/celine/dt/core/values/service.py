from __future__ import annotations

import logging
from typing import Any, Mapping

from celine.dt.core.values.executor import FetchResult, ValuesFetcher
from celine.dt.core.values.registry import ValuesRegistry, FetcherDescriptor

logger = logging.getLogger(__name__)


class ValuesService:
    """Facade for values fetchers.

    This service is the single entry point for data retrieval within apps.
    It wraps registry resolution and fetch execution, returning FetchResult
    for consistency across transports.
    """

    def __init__(
        self,
        *,
        registry: ValuesRegistry,
        fetcher: ValuesFetcher,
    ) -> None:
        self._registry = registry
        self._fetcher = fetcher

    @property
    def registry(self) -> ValuesRegistry:
        return self._registry

    def list(self) -> list[dict[str, Any]]:
        return self._registry.list()

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
        request_scope: Mapping[str, Any] | None = None,
    ) -> FetchResult:
        """Fetch data using a registered value fetcher.

        Args:
            fetcher_id: Fully-qualified fetcher identifier.
            payload: Input parameters (validated by the fetcher schema when defined).
            limit: Optional pagination limit.
            offset: Optional pagination offset.
            request_scope: Optional request-scoped context. Currently unused by the
                core executor but reserved for future adaptations (e.g., auth-based
                row filtering or audit metadata).

        Returns:
            FetchResult with items + pagination metadata.

        Raises:
            KeyError: if fetcher is missing.
            ValueError / ValidationError: for invalid payload.
            Exception: for unexpected execution errors.
        """
        # request_scope is accepted for contract stability even if not used today.
        _ = request_scope

        descriptor = self._registry.get(fetcher_id)

        logger.debug(
            "Values fetch: id=%s limit=%s offset=%s",
            fetcher_id,
            limit,
            offset,
        )

        return await self._fetcher.fetch(
            descriptor=descriptor,
            payload=dict(payload),
            limit=limit,
            offset=offset,
        )
