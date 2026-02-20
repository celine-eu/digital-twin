# celine/dt/core/broker/decorators.py
from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext, RouteDef

# Works for both plain functions and bound methods.
# Plain function:  async def handler(event, ctx) -> None
# Domain method:   async def handler(self, event, ctx) -> None
AnyHandler = Callable[..., Awaitable[None]]


def on_event(
    event_type: str,
    *,
    topics: list[str],
    broker: str | None = None,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Callable[[AnyHandler], AnyHandler]:
    """Declare a handler for a broker event.

    Works on plain module-level functions and DTDomain methods alike::

        # plain function in any .py file
        @on_event("pipeline.run.completed", topics=["celine/pipelines/runs/+"])
        async def on_run_completed(event: DTEvent, ctx: EventContext) -> None:
            ...

        # domain method
        class MyDomain(DTDomain):
            @on_event("something", topics=["celine/something/+"])
            async def on_something(self, event: DTEvent, ctx: EventContext) -> None:
                ...
    """
    def _decorator(fn: AnyHandler) -> AnyHandler:
        setattr(
            fn,
            "_dt_route",
            RouteDef(
                event_type=event_type,
                topics=list(topics),
                broker=broker,
                enabled=enabled,
                metadata=metadata or {},
                handlers=[],
            ),
        )
        return fn

    return _decorator