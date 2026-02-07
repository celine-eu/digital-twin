# celine/dt/core/context.py
"""
RunContext – per-request execution context.

Carries request-scoped data (entity info, request ID, timestamp) while
providing access to application-scoped services (values, broker, components).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from celine.dt.contracts.entity import EntityInfo

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Immutable per-request context available to all domain code.

    Attributes:
        request_id: Unique identifier for this invocation.
        now: Request timestamp (UTC).
        entity: Resolved entity from the URL path (may be ``None`` for
            non-entity-scoped calls).
        values_service: The :class:`ValuesService` for data fetching.
        broker_service: The :class:`BrokerService` for event publishing.
        services: Shared service bag (clients_registry, etc.).
        workspace: Set by the simulation runner for scenario/run operations.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entity: EntityInfo | None = None
    values_service: Any = None
    broker_service: Any = None
    services: dict[str, Any] = field(default_factory=dict)
    workspace: Any = None

    # -- convenience --------------------------------------------------------

    async def fetch_value(
        self,
        fetcher_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        """Shortcut to fetch data through the values service.

        Automatically injects entity context into the template rendering.
        """
        if self.values_service is None:
            raise RuntimeError("Values service not available in this context")

        return await self.values_service.fetch(
            fetcher_id=fetcher_id,
            payload=dict(payload) if payload else {},
            limit=limit,
            offset=offset,
            entity=self.entity,
        )

    async def publish_event(
        self,
        topic: str,
        payload: Any,
        *,
        broker_name: str | None = None,
    ) -> Any:
        """Publish an event through the broker service."""
        if self.broker_service is None:
            logger.debug("No broker service, event not published on topic=%s", topic)
            return None
        return await self.broker_service.publish_event(
            topic=topic,
            payload=payload,
            broker_name=broker_name,
        )

    def get_service(self, name: str) -> Any:
        """Retrieve a named service from the shared bag."""
        svc = self.services.get(name)
        if svc is None:
            raise KeyError(f"Service '{name}' not found in context")
        return svc
