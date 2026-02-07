# celine/dt/contracts/subscription.py
"""
Subscription contracts for reactive event handling within domains.

A subscription binds MQTT topic patterns to async handler functions.
Topic templates may contain ``{entity_id}`` which is expanded per-entity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from celine.dt.contracts.events import DTEvent


@dataclass(frozen=True)
class EventContext:
    """Context delivered alongside every received event."""

    topic: str
    broker_name: str
    received_at: datetime
    entity_id: str | None = None
    message_id: str | None = None
    raw_payload: bytes | None = None


EventHandler = Callable[[DTEvent, EventContext], Awaitable[None]]  # type: ignore[type-arg]


@dataclass
class SubscriptionSpec:
    """Declarative subscription: topic patterns → handler."""

    topics: list[str]
    handler: EventHandler
    id: str = field(default_factory=lambda: f"sub-{uuid4().hex[:8]}")
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
