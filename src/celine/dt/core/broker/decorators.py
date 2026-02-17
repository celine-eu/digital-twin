from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar, Union
from typing_extensions import Concatenate, ParamSpec

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext, RouteDef

SelfT = TypeVar("SelfT")
EventMethod = Callable[[SelfT, DTEvent[Any], EventContext], Awaitable[None]]


def on_event(
    event_type: str,
    *,
    topics: list[str],
    broker: str | None = None,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Callable[[EventMethod[SelfT]], EventMethod[SelfT]]:
    def _decorator(fn: EventMethod[SelfT]) -> EventMethod[SelfT]:
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
