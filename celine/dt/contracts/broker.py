# celine/dt/contracts/broker.py
"""
Broker contract for Digital Twin event publishing and subscription.

The broker abstraction enables DT apps to emit computed events to external
systems and receive events, without coupling to a specific transport
(MQTT, Kafka, RabbitMQ, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


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


@dataclass
class SubscribeResult:
    """
    Result of a subscribe operation.

    Attributes:
        success: Whether the subscription succeeded.
        subscription_id: Identifier for this subscription (for unsubscribe).
        error: Error message if subscription failed.
    """

    success: bool
    subscription_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ReceivedMessage:
    """
    A message received from the broker.

    Attributes:
        topic: The topic the message arrived on.
        payload: Parsed message payload.
        raw_payload: Original message bytes.
        qos: QoS level the message was delivered with.
        message_id: Broker-assigned message ID (if available).
        timestamp: When the message was received.
    """

    topic: str
    payload: dict[str, Any]
    raw_payload: bytes
    qos: QoS = QoS.AT_LEAST_ONCE
    message_id: str | None = None
    timestamp: datetime | None = None


# Type alias for message handlers
MessageHandler = Callable[[ReceivedMessage], Awaitable[None]]


@runtime_checkable
class Broker(Protocol):
    """
    Protocol for message brokers.

    Implementations must provide async publish and subscribe capabilities.
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

        Should flush any pending messages and cancel subscriptions before disconnecting.
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

    async def subscribe(
        self,
        topics: list[str],
        handler: MessageHandler,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> SubscribeResult:
        """
        Subscribe to topics and register a message handler.

        Args:
            topics: List of topic patterns (supports wildcards like + and #).
            handler: Async callback invoked for each received message.
            qos: Quality of Service level for the subscription.

        Returns:
            SubscribeResult with subscription_id for later unsubscribe.
        """
        ...

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from a previous subscription.

        Args:
            subscription_id: The ID returned from subscribe().

        Returns:
            True if unsubscribed successfully, False if not found.
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

    @abstractmethod
    async def subscribe(
        self,
        topics: list[str],
        handler: MessageHandler,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> SubscribeResult:
        """Subscribe to topics."""
        ...

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from topics."""
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
