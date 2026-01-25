# celine/dt/core/subscription/dispatcher.py
"""
Event dispatcher for routing events to subscription handlers.

The dispatcher receives events and concurrently invokes all matching
subscription handlers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext, EventHandler, Subscription
from celine.dt.core.subscription.registry import SubscriptionRegistry

logger = logging.getLogger(__name__)


class EventDispatcher:
    """
    Dispatches events to matching subscription handlers.

    Features:
    - Concurrent handler execution
    - Error isolation (one handler failure doesn't affect others)
    - Configurable concurrency limits
    - Dispatch metrics/logging

    Example:
        dispatcher = EventDispatcher(registry=subscription_registry)

        # Dispatch an event (called by subscriber when message arrives)
        await dispatcher.dispatch(event, context)
    """

    def __init__(
        self,
        registry: SubscriptionRegistry,
        max_concurrent: int = 100,
    ) -> None:
        """
        Initialize the dispatcher.

        Args:
            registry: The subscription registry to use for matching.
            max_concurrent: Maximum concurrent handler invocations.
        """
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._dispatch_count = 0
        self._error_count = 0

    @property
    def registry(self) -> SubscriptionRegistry:
        """Get the subscription registry."""
        return self._registry

    @property
    def dispatch_count(self) -> int:
        """Total number of events dispatched."""
        return self._dispatch_count

    @property
    def error_count(self) -> int:
        """Total number of handler errors."""
        return self._error_count

    async def dispatch(
        self,
        event: DTEvent,
        context: EventContext,
    ) -> int:
        """
        Dispatch an event to all matching handlers.

        Handlers are invoked concurrently. Errors in individual handlers
        are logged but don't affect other handlers.

        Args:
            event: The event to dispatch.
            context: The event context (topic, broker, etc.).

        Returns:
            Number of handlers invoked.
        """
        self._dispatch_count += 1

        # Find matching subscriptions
        matching = self._registry.get_matching(context.topic)

        if not matching:
            logger.debug(
                "No subscriptions match topic '%s'",
                context.topic,
            )
            return 0

        logger.debug(
            "Dispatching event to %d subscription(s) for topic '%s'",
            len(matching),
            context.topic,
        )

        # Invoke all handlers concurrently
        tasks = [
            self._invoke_handler(sub, event, context)
            for sub in matching
            if sub.handler is not None
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return len(tasks)

    async def _invoke_handler(
        self,
        subscription: Subscription,
        event: DTEvent,
        context: EventContext,
    ) -> None:
        """
        Invoke a single handler with error isolation.

        Errors are logged but not re-raised to ensure other handlers
        can still execute.
        """

        if subscription.handler is None:
            logger.warning(
                "Handler '%s' is None for event on '%s'",
                subscription.id,
                context.topic,
            )
            return None

        async with self._semaphore:
            try:
                await subscription.handler(event, context)

                logger.debug(
                    "Handler '%s' completed for event on '%s'",
                    subscription.id,
                    context.topic,
                )

            except Exception as exc:
                self._error_count += 1

                logger.error(
                    "Handler '%s' failed for event on '%s': %s",
                    subscription.id,
                    context.topic,
                    exc,
                    exc_info=True,
                )

    async def dispatch_raw(
        self,
        topic: str,
        payload: dict[str, Any],
        broker_name: str,
        message_id: str | None = None,
        raw_payload: bytes | None = None,
    ) -> int:
        """
        Dispatch a raw message (convenience method).

        Parses the payload into a DTEvent and creates the context.

        Args:
            topic: The topic the message arrived on.
            payload: Parsed JSON payload.
            broker_name: Name of the source broker.
            message_id: Optional message ID.
            raw_payload: Optional raw bytes.

        Returns:
            Number of handlers invoked.
        """
        # Create event context
        context = EventContext(
            topic=topic,
            broker_name=broker_name,
            received_at=datetime.now(timezone.utc),
            message_id=message_id,
            raw_payload=raw_payload,
        )

        # Parse payload into generic DTEvent
        # Note: For type-specific handling, handlers can inspect @type
        event = self._parse_event(payload)

        return await self.dispatch(event, context)

    def _parse_event(self, payload: dict[str, Any]) -> DTEvent:
        """
        Parse a raw payload into a DTEvent.

        For now, creates a generic DTEvent. Handlers can use the type
        property to determine the specific event type if needed.
        """
        from celine.dt.contracts.events import EventSource
        from pydantic import BaseModel

        # Create a minimal event wrapper
        # The payload itself might already be a full DTEvent structure
        event_type = (
            payload.get("@type") or payload.get("event_type") or payload.get("type")
        )

        if event_type:
            # Payload is already event-shaped, wrap minimally
            class GenericPayload(BaseModel):
                model_config = {"extra": "allow"}

            # Extract source if present
            source_data = payload.get("source", {})
            source = EventSource(
                app_key=source_data.get("app_key", "unknown"),
                app_version=source_data.get("app_version", "unknown"),
                module=source_data.get("module"),
                instance_id=source_data.get("instance_id"),
            )

            # Build event using field name (populate_by_name=True allows this)
            event = DTEvent[GenericPayload](
                event_type=event_type,
                id=payload.get("id", ""),
                source=source,
                timestamp=payload.get("timestamp", datetime.now(timezone.utc)),
                correlation_id=payload.get("correlation_id"),
                payload=GenericPayload(**payload.get("payload", {})),
                metadata=payload.get("metadata", {}),
            )
            return event
        else:
            # Raw payload, wrap it
            class RawPayload(BaseModel):
                data: dict[str, Any]

            source = EventSource(app_key="unknown", app_version="unknown")
            return DTEvent[RawPayload](
                event_type="unknown",
                source=source,
                payload=RawPayload(data=payload),
            )

    def reset_counters(self) -> None:
        """Reset dispatch and error counters."""
        self._dispatch_count = 0
        self._error_count = 0
