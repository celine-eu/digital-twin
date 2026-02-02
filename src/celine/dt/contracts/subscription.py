# celine/dt/contracts/subscription.py
"""
Subscription contracts for Digital Twin event reception.

These contracts define the interfaces for subscribing to events from brokers
and handling them within the DT runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable
from uuid import uuid4

from celine.dt.contracts.events import DTEvent


@dataclass(frozen=True)
class EventContext:
    """
    Context provided to event handlers along with the event.

    Attributes:
        topic: The actual topic the message arrived on (after wildcard resolution).
        broker_name: Name of the broker that delivered this event.
        received_at: Timestamp when the event was received.
        message_id: Broker-assigned message ID (if available).
        raw_payload: Original message bytes for advanced use cases.
    """

    topic: str
    broker_name: str
    received_at: datetime
    message_id: str | None = None
    raw_payload: bytes | None = None


# Type alias for event handlers
# Handler receives the parsed event and context, returns nothing
EventHandler = Callable[[DTEvent, EventContext], Awaitable[None]]


@dataclass
class Subscription:
    """
    A subscription to one or more event topics.

    Attributes:
        id: Unique subscription identifier.
        topics: List of topic patterns (supports MQTT wildcards: + and #).
        handler: Async function to call when events match.
        enabled: Whether this subscription is active.
        metadata: Optional metadata for debugging/monitoring.
    """

    id: str = field(default_factory=lambda: f"sub-{uuid4().hex[:8]}")
    topics: list[str] = field(default_factory=list)
    handler: EventHandler | None = None
    handler_path: str | None = None  # Import path for YAML-configured handlers
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches_topic(self, topic: str) -> bool:
        """
        Check if a topic matches any of this subscription's patterns.

        Supports MQTT-style wildcards:
        - '+' matches exactly one level
        - '#' matches zero or more levels (must be last)

        Examples:
            "dt/ev-charging/+/readiness" matches "dt/ev-charging/rec-folgaria/readiness"
            "dt/ev-charging/#" matches "dt/ev-charging/rec-folgaria/readiness"
        """
        for pattern in self.topics:
            if self._topic_matches_pattern(topic, pattern):
                return True
        return False

    @staticmethod
    def _topic_matches_pattern(topic: str, pattern: str) -> bool:
        """Check if a single topic matches a single pattern."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        i = 0
        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == "#":
                # '#' matches everything from here
                return True

            if i >= len(topic_parts):
                # Topic is shorter than pattern
                return False

            if pattern_part == "+":
                # '+' matches exactly one level
                continue

            if pattern_part != topic_parts[i]:
                # Literal mismatch
                return False

        # Check if we consumed all topic parts
        return i + 1 == len(topic_parts)


@runtime_checkable
class SubscriptionRegistry(Protocol):
    """Protocol for subscription registries."""

    def register(self, subscription: Subscription) -> str:
        """Register a subscription, returns subscription ID."""
        ...

    def unregister(self, subscription_id: str) -> bool:
        """Unregister a subscription, returns True if found."""
        ...

    def get(self, subscription_id: str) -> Subscription | None:
        """Get a subscription by ID."""
        ...

    def get_matching(self, topic: str) -> list[Subscription]:
        """Get all subscriptions matching a topic."""
        ...

    def list_all(self) -> list[Subscription]:
        """List all registered subscriptions."""
        ...


@runtime_checkable
class EventDispatcher(Protocol):
    """Protocol for event dispatchers."""

    async def dispatch(self, event: DTEvent, context: EventContext) -> None:
        """Dispatch an event to all matching handlers."""
        ...


@dataclass
class SubscriptionResult:
    """
    Result of a subscription operation.

    Attributes:
        success: Whether the operation succeeded.
        subscription_id: The subscription ID (for successful registrations).
        error: Error message if operation failed.
    """

    success: bool
    subscription_id: str | None = None
    error: str | None = None
