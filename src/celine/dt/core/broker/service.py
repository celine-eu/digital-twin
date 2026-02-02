# celine/dt/core/broker/service.py
"""
Broker service for Digital Twin event publishing.

The BrokerService is the primary interface for DT apps to publish events.
It manages broker connections, handles failover, and provides high-level
methods for publishing typed events.
"""
from __future__ import annotations

import logging
from typing import Any

from celine.sdk.broker.contracts import Broker, BrokerMessage, PublishResult, QoS
from celine.dt.core.broker.registry import BrokerRegistry

logger = logging.getLogger(__name__)


class BrokerService:
    """
    High-level service for event publishing.

    The BrokerService provides:
    - Connection lifecycle management for all registered brokers
    - High-level methods for publishing typed events
    - Broker selection (default or named)
    - Error handling and logging

    Example:
        broker_service = BrokerService(registry=broker_registry)

        # Connect all brokers on startup
        await broker_service.connect_all()

        # Publish an event
        result = await broker_service.publish_event(
            event=ev_charging_event,
            topic="dt/ev-charging/rec-folgaria/readiness",
        )

        # Disconnect on shutdown
        await broker_service.disconnect_all()
    """

    def __init__(self, registry: BrokerRegistry) -> None:
        """
        Initialize the broker service.

        Args:
            registry: Registry containing broker instances.
        """
        self._registry = registry

    @property
    def registry(self) -> BrokerRegistry:
        """Get the broker registry."""
        return self._registry

    def has_brokers(self) -> bool:
        """Check if any brokers are registered."""
        return len(self._registry) > 0

    async def connect_all(self) -> dict[str, bool]:
        """
        Connect all registered brokers.

        Returns:
            Dict mapping broker name to connection success.
        """
        results: dict[str, bool] = {}

        for name, broker in self._registry.items():
            try:
                await broker.connect()
                results[name] = True
                logger.info("Connected broker: %s", name)
            except Exception as exc:
                results[name] = False
                logger.error("Failed to connect broker '%s': %s", name, exc)

        return results

    async def disconnect_all(self) -> None:
        """Disconnect all registered brokers."""
        for name, broker in self._registry.items():
            try:
                await broker.disconnect()
                logger.info("Disconnected broker: %s", name)
            except Exception as exc:
                logger.warning("Error disconnecting broker '%s': %s", name, exc)

    def get_broker(self, name: str | None = None) -> Broker:
        """
        Get a broker by name or the default.

        Args:
            name: Broker name, or None for default.

        Returns:
            The broker instance.

        Raises:
            KeyError: If broker not found.
        """
        return self._registry.get(name)

    async def publish(
        self,
        message: BrokerMessage,
        broker_name: str | None = None,
    ) -> PublishResult:
        """
        Publish a message using the specified or default broker.

        Args:
            message: The message to publish.
            broker_name: Optional broker name. Uses default if None.

        Returns:
            PublishResult indicating success or failure.
        """
        if not self.has_brokers():
            logger.warning("No brokers configured, message not published")
            return PublishResult(
                success=False,
                error="No brokers configured",
            )

        try:
            broker = self.get_broker(broker_name)
        except KeyError as exc:
            return PublishResult(
                success=False,
                error=str(exc),
            )

        return await broker.publish(message)

    async def publish_event(
        self,
        event: Any,
        topic: str | None = None,
        broker_name: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ) -> PublishResult:
        """
        Publish a typed event (Pydantic model).

        This is the recommended method for publishing DT events.

        Args:
            event: A Pydantic model (e.g., DTEvent subclass).
            topic: Override topic. If None, derives from event.
            broker_name: Optional broker name. Uses default if None.
            qos: Quality of Service level.
            retain: Whether to retain the message.

        Returns:
            PublishResult indicating success or failure.
        """
        if not self.has_brokers():
            logger.warning("No brokers configured, event not published")
            return PublishResult(
                success=False,
                error="No brokers configured",
            )

        # Derive topic from event if not provided
        if topic is None:
            topic = self._derive_topic(event)

        # Serialize event
        if hasattr(event, "model_dump"):
            payload = event.model_dump(mode="json", by_alias=True)
        elif hasattr(event, "dict"):
            payload = event.dict(by_alias=True)
        else:
            payload = dict(event)

        message = BrokerMessage(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=retain,
            correlation_id=getattr(event, "correlation_id", None),
            timestamp=getattr(event, "timestamp", None),
        )

        return await self.publish(message, broker_name)

    def _derive_topic(self, event: Any) -> str:
        """
        Derive a topic from an event.

        Convention: dt/{module}/{event-type}/{entity-id}

        Examples:
            - dt.ev-charging.readiness-computed -> dt/ev-charging/readiness-computed/{community_id}
            - dt.app.execution-completed -> dt/app/execution-completed/{app_key}
        """
        event_type = getattr(event, "type", None)

        if not event_type:
            return "dt/events/unknown"

        # Convert type to path: "dt.ev-charging.readiness-computed" -> "ev-charging/readiness-computed"
        type_path = event_type.replace("dt.", "").replace(".", "/")

        # Try to extract entity ID from payload
        payload = getattr(event, "payload", None)
        entity_id = "default"

        if payload:
            # Common entity ID fields
            for field in ["community_id", "app_key", "alert_id"]:
                if hasattr(payload, field):
                    entity_id = getattr(payload, field)
                    break

        return f"dt/{type_path}/{entity_id}"

    async def publish_to_all(
        self,
        message: BrokerMessage,
    ) -> dict[str, PublishResult]:
        """
        Publish a message to all registered brokers.

        Useful for broadcasting important events or for redundancy.

        Args:
            message: The message to publish.

        Returns:
            Dict mapping broker name to PublishResult.
        """
        results: dict[str, PublishResult] = {}

        for name, broker in self._registry.items():
            results[name] = await broker.publish(message)

        return results


class NullBrokerService(BrokerService):
    """
    No-op broker service for testing or when brokers are disabled.

    All publish operations succeed but don't actually send messages.
    """

    def __init__(self) -> None:
        # Don't call super().__init__ since we don't need a registry
        self._registry = BrokerRegistry()

    def has_brokers(self) -> bool:
        return False

    async def connect_all(self) -> dict[str, bool]:
        return {}

    async def disconnect_all(self) -> None:
        pass

    async def publish(
        self,
        message: BrokerMessage,
        broker_name: str | None = None,
    ) -> PublishResult:
        logger.debug("NullBrokerService: would publish to %s", message.topic)
        return PublishResult(success=True, message_id="null")

    async def publish_event(
        self,
        event: Any,
        topic: str | None = None,
        broker_name: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ) -> PublishResult:
        logger.debug("NullBrokerService: would publish event to %s", topic)
        return PublishResult(success=True, message_id="null")
