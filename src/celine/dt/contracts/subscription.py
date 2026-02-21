# celine/dt/contracts/subscription.py
"""
Subscription contracts for reactive event handling.

A subscription binds MQTT topic patterns to async handler functions.
Handlers can be plain module-level functions or bound methods on a DTDomain.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, runtime_checkable
from uuid import uuid4


from celine.dt.contracts import DTEvent

if TYPE_CHECKING:
    from celine.dt.core.clients.registry import ClientsRegistry
    from celine.dt.core.domain.registry import DomainRegistry
    from celine.dt.contracts import Infrastructure
    from celine.dt.core.broker.service import BrokerService
    from celine.dt.core.domain.base import DTDomain
    from celine.dt.core.values.service import ValuesService


@dataclass(frozen=True)
class EventContext:
    """Context delivered alongside every received event.

    Available in every handler — both domain methods and plain functions::

        @on_event("pipeline.run.completed", topics=["celine/pipelines/runs/+"])
        async def on_run_completed(event: DTEvent, ctx: EventContext) -> None:
            users = await ctx.values.fetch("pipeline-reactor.affected_users", {...})
            await ctx.broker.publish_event(topic=f"celine/nudging/{user_id}", payload={...})
    """
    topic: str
    broker_name: str
    received_at: datetime
    infra: Infrastructure
    entity_id: str | None = None
    message_id: str | None = None
    raw_payload: bytes | None = None

    def get_dt(self, domain_type: str) -> DTDomain:
        return self.infra.domain_registry.get_by_type(domain_type)


EventHandler = Callable[[DTEvent, EventContext], Awaitable[None]]  # type: ignore[type-arg]


@dataclass
class SubscriptionSpec:
    """Declarative subscription: topic patterns → handler(s)."""

    topics: list[str]
    handlers: list[EventHandler]
    id: str = field(default_factory=lambda: f"sub-{uuid4().hex[:8]}")
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventRoute:
    event_type: str
    topics: list[str]
    broker: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    handlers: list[EventHandler] = field(default_factory=list)


@runtime_checkable
class DomainHandler(Protocol):
    async def __call__(self, event: DTEvent[Any], ctx: EventContext) -> None: ...


@dataclass(frozen=True)
class RouteDef:
    event_type: str
    topics: list[str]
    broker: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    handlers: list[EventHandler] = field(default_factory=list)

    def with_handler(self, h: EventHandler) -> "RouteDef":
        return replace(self, handlers=[*self.handlers, h])