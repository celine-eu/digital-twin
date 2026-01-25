# celine/dt/contracts/broker.py
"""
Broker contract for Digital Twin event publishing.

The broker abstraction enables DT apps to emit computed events to external
systems without coupling to a specific transport (MQTT, Kafka, RabbitMQ, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class QoS(int, Enum):
    """Quality of Service levels for message delivery."""

    AT_MOST_ONCE = 0  # Fire and forget
    AT_LEAST_ONCE = 1  # Acknowledged delivery
    EXACTLY_ONCE = 2  # Guaranteed single delivery


@dataclass(frozen=True)
class BrokerMessage:
    """
    A message to be published via the broker.

    Attributes:
        topic: The destination topic/channel for the message.
        payload: The message payload (will be serialized to JSON).
        qos: Quality of Service level for delivery.
        retain: Whether the broker should retain the message.
        headers: Optional metadata headers.
        correlation_id: Optional ID for request-response correlation.
        timestamp: Message creation timestamp (auto-set if not provided).
    """

    topic: str
    payload: dict[str, Any]
    qos: QoS = QoS.AT_LEAST_ONCE
    retain: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: datetime | None = None


@dataclass
class PublishResult:
    """
    Result of a publish operation.

    Attributes:
        success: Whether the publish succeeded.
        message_id: Broker-assigned message ID (if available).
        error: Error message if publish failed.
    """

    success: bool
    message_id: str | None = None
    error: str | None = None


@runtime_checkable
class Broker(Protocol):
    """
    Protocol for message brokers.

    Implementations must provide async publish capabilities.
    Connection lifecycle is managed by the implementation.
    """

    async def connect(self) -> None:
        """
        Establish connection to the broker.

        Implementations should handle reconnection internally.
        This method is idempotent - calling it when already connected is safe.
        """
        ...

    async def disconnect(self) -> None:
        """
        Gracefully disconnect from the broker.

        Should flush any pending messages before disconnecting.
        """
        ...

    async def publish(self, message: BrokerMessage) -> PublishResult:
        """
        Publish a message to the broker.

        Args:
            message: The message to publish.

        Returns:
            PublishResult indicating success or failure.
        """
        ...

    @property
    def is_connected(self) -> bool:
        """Check if the broker connection is active."""
        ...


class BrokerBase(ABC):
    """
    Abstract base class for broker implementations.

    Provides common functionality and enforces the Broker protocol.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""
        ...

    @abstractmethod
    async def publish(self, message: BrokerMessage) -> PublishResult:
        """Publish a message."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        ...

    async def __aenter__(self) -> "BrokerBase":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
