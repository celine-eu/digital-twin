# celine/dt/contracts/broker.py
"""
Broker protocol for event publishing.

Broker implementations (MQTT, etc.) conform to this protocol.
The DT core does not depend on any specific transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol, runtime_checkable


class QoS(IntEnum):
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


@dataclass(frozen=True)
class PublishResult:
    success: bool
    broker_name: str = ""
    topic: str = ""
    error: str | None = None


@runtime_checkable
class Broker(Protocol):
    """Transport-agnostic message broker."""

    async def connect(self) -> bool: ...
    async def disconnect(self) -> None: ...
    async def publish(self, topic: str, payload: bytes, qos: QoS = QoS.AT_LEAST_ONCE) -> PublishResult: ...
    async def subscribe(self, topic: str, handler: Any) -> None: ...

    @property
    def is_connected(self) -> bool: ...
