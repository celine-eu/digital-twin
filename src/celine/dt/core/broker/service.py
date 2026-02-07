# celine/dt/core/broker/service.py
"""
BrokerService – manages broker connections and event publishing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from celine.dt.contracts.broker import Broker, PublishResult, QoS

logger = logging.getLogger(__name__)


class BrokerService:
    """Manages named broker instances and delegates publish operations."""

    def __init__(self) -> None:
        self._brokers: dict[str, Broker] = {}
        self._default: str | None = None

    def register(self, name: str, broker: Broker) -> None:
        if name in self._brokers:
            raise ValueError(f"Broker '{name}' already registered")
        self._brokers[name] = broker
        if self._default is None:
            self._default = name
        logger.info("Registered broker: %s", name)

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
            raise KeyError(f"Broker '{target}' not found")

    async def connect_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, broker in self._brokers.items():
            try:
                ok = await broker.connect()
                results[name] = ok
                if ok:
                    logger.info("Broker '%s' connected", name)
                else:
                    logger.warning("Broker '%s' connect returned False", name)
            except Exception:
                logger.exception("Broker '%s' connection failed", name)
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        for name, broker in self._brokers.items():
            try:
                await broker.disconnect()
                logger.info("Broker '%s' disconnected", name)
            except Exception:
                logger.exception("Broker '%s' disconnect failed", name)

    async def publish_event(
        self,
        *,
        topic: str,
        payload: Any,
        broker_name: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> PublishResult:
        """Serialize and publish an event to the specified (or default) broker."""
        broker = self.get(broker_name)

        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {"value": str(payload)}

        raw = json.dumps(data, default=str).encode("utf-8")

        try:
            result = await broker.publish(topic, raw, qos)
            logger.debug("Published to %s (broker=%s, success=%s)", topic, broker_name, result.success)
            return result
        except Exception as exc:
            logger.exception("Publish failed on topic=%s", topic)
            return PublishResult(
                success=False,
                broker_name=broker_name or self._default or "",
                topic=topic,
                error=str(exc),
            )


class NullBrokerService(BrokerService):
    """No-op broker for environments without message infrastructure."""

    def has_brokers(self) -> bool:
        return False

    async def publish_event(self, **_: Any) -> PublishResult:
        return PublishResult(success=False, error="No broker configured")
