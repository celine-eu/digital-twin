# celine/dt/core/broker/service.py
"""
BrokerService – manages named SDK broker instances.

Wraps ``celine.sdk.broker.MqttBroker`` (or any ``Broker`` implementation)
with a named registry, default selection, and convenience publish methods.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from celine.sdk.broker import (
    Broker,
    BrokerMessage,
    PublishResult,
    QoS,
    MessageHandler,
    SubscribeResult,
)

logger = logging.getLogger(__name__)


class BrokerService:
    """Named registry of SDK broker instances with lifecycle management."""

    def __init__(self) -> None:
        self._brokers: dict[str, Broker] = {}
        self._default: str | None = None

    def register(self, name: str, broker: Broker) -> None:
        if name in self._brokers:
            raise ValueError(f"Broker '{name}' already registered")
        self._brokers[name] = broker
        if self._default is None:
            self._default = name
        logger.info("Registered broker: %s (%s)", name, type(broker).__name__)

    def set_default(self, name: str) -> None:
        if name not in self._brokers:
            raise KeyError(f"Broker '{name}' not registered")
        self._default = name

    def has_brokers(self) -> bool:
        return len(self._brokers) > 0

    def get(self, name: str | None = None) -> Broker:
        target = name or self._default
        if target is None:
            raise KeyError("No default broker configured")
        try:
            return self._brokers[target]
        except KeyError:
            raise KeyError(
                f"Broker '{target}' not found. Available: {list(self._brokers)}"
            )

    async def connect_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, broker in self._brokers.items():
            try:
                await broker.connect()
                results[name] = broker.is_connected
                if broker.is_connected:
                    logger.info("Broker '%s' connected", name)
                else:
                    logger.warning(
                        "Broker '%s' connect did not establish connection", name
                    )
            except Exception as e:
                logger.error("Broker '%s' connection failed: %s", name, str(e))
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        for name, broker in self._brokers.items():
            try:
                await broker.disconnect()
                logger.info("Broker '%s' disconnected", name)
            except Exception:
                logger.exception("Broker '%s' disconnect error", name)

    async def publish_event(
        self,
        *,
        topic: str,
        payload: Any,
        broker_name: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ) -> PublishResult:
        """Serialize and publish a domain event via the SDK broker.

        Accepts Pydantic models, dicts, or primitives as payload.
        """
        broker = self.get(broker_name)

        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {"value": str(payload)}

        message = BrokerMessage(
            topic=topic,
            payload=data,
            qos=qos,
            retain=retain,
        )

        try:
            result = await broker.publish(message)
            logger.debug(
                "Published to %s (broker=%s, success=%s)",
                topic,
                broker_name or self._default,
                result.success,
            )
            return result
        except Exception as exc:
            logger.exception("Publish failed on topic=%s", topic)
            return PublishResult(success=False, error=str(exc))

    async def subscribe(
        self,
        *,
        topics: list[str],
        handler: MessageHandler,
        broker_name: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> SubscribeResult:
        broker: Broker = self.get(broker_name)
        return await broker.subscribe(topics=topics, handler=handler, qos=qos)

    async def unsubscribe(
        self,
        *,
        subscription_id: str,
        broker_name: str | None = None,
    ) -> bool:
        broker: Broker = self.get(broker_name)
        return await broker.unsubscribe(subscription_id)


class NullBrokerService(BrokerService):
    """No-op service for environments without message infrastructure."""

    def has_brokers(self) -> bool:
        return False

    async def publish_event(self, **_: Any) -> PublishResult:
        return PublishResult(success=False, error="No broker configured")
