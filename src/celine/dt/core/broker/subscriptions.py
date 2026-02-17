from __future__ import annotations

from datetime import timezone, datetime

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from celine.sdk.broker import QoS, ReceivedMessage, SubscribeResult
from celine.dt.contracts.subscription import EventContext, SubscriptionSpec
from celine.dt.core.broker.service import BrokerService
from celine.dt.core.domain.base import DTDomain
from celine.dt.contracts.events import DTEvent, EventSource

logger = logging.getLogger(__name__)


@dataclass
class ActiveSubscription:
    domain_name: str
    spec_id: str
    topics: list[str]
    subscription_id: str
    broker_name: str | None


class AnyPayload(BaseModel):
    """Fallback payload wrapper for arbitrary JSON objects."""

    model_config = ConfigDict(extra="allow")


def _dt_event_from_received(
    *,
    domain: DTDomain,
    spec: SubscriptionSpec,
    msg: ReceivedMessage,
) -> DTEvent[AnyPayload]:
    """
    Build a DTEvent[AnyPayload] from an SDK ReceivedMessage.

    Supports two formats:
    1) Native DTEvent JSON (serializer uses '@type', '@context', 'source', 'payload', ...)
    2) Raw JSON payload (wrapped into a DTEvent with event_type derived from metadata/topic)
    """
    data = msg.payload if isinstance(msg.payload, dict) else {}

    # Format 1: DTEvent serialized form uses "@type" and "@context"
    if "@type" in data or "event_type" in data:
        mapped: dict[str, Any] = dict(data)

        if "@type" in mapped and "event_type" not in mapped:
            mapped["event_type"] = mapped.pop("@type")

        if "@context" in mapped and "context" not in mapped:
            mapped["context"] = mapped.pop("@context")

        # Ensure required fields exist
        if "source" not in mapped or not isinstance(mapped["source"], dict):
            mapped["source"] = {"domain": domain.name}

        if "payload" not in mapped:
            mapped["payload"] = {}

        # Coerce payload dict into AnyPayload
        payload_obj = (
            AnyPayload.model_validate(mapped["payload"])
            if isinstance(mapped["payload"], dict)
            else AnyPayload()
        )
        mapped["payload"] = payload_obj

        # Validate into DTEvent[AnyPayload]
        return DTEvent[AnyPayload].model_validate(mapped)

    # Format 2: raw payload, wrap it
    event_type = (
        spec.metadata.get("event_type") or spec.metadata.get("event_name") or msg.topic
    )

    source = EventSource(
        domain=spec.metadata.get("source_domain") or domain.name,
        entity_id=spec.metadata.get("entity_id"),
        handler=spec.metadata.get("handler"),
        version=spec.metadata.get("version", "unknown"),
    )

    payload = AnyPayload.model_validate(data)

    return DTEvent[AnyPayload](
        event_type=str(event_type),
        source=source,
        payload=payload,
        metadata={"subscription_id": spec.id, **(spec.metadata or {})},
    )


def _event_context_from_received(
    *,
    spec: SubscriptionSpec,
    msg: ReceivedMessage,
    broker_name: str,
) -> EventContext:
    received_at = msg.timestamp or datetime.now(timezone.utc)

    return EventContext(
        topic=msg.topic,
        broker_name=broker_name,
        received_at=received_at,
        entity_id=spec.metadata.get("entity_id"),
        message_id=msg.message_id,
        raw_payload=msg.raw_payload,
    )


class SubscriptionManager:
    """
    Collects SubscriptionSpec from domains and materializes them into SDK broker subscriptions.
    """

    def __init__(
        self,
        *,
        broker_service: BrokerService,
        domains: list[DTDomain],
        default_qos: QoS = QoS.AT_LEAST_ONCE,
        default_broker_name: str | None = None,
    ) -> None:
        self._broker_service = broker_service
        self._domains = domains
        self._default_qos = default_qos
        self._default_broker_name = default_broker_name
        self._active: list[ActiveSubscription] = []

    async def start(self) -> None:
        for domain in self._domains:
            specs = domain.get_subscriptions() or []
            for spec in specs:
                if not spec.enabled:
                    logger.info(
                        "Subscription disabled: domain=%s spec=%s", domain.name, spec.id
                    )
                    continue

                topics = self._expand_topics(spec.topics)
                if not topics:
                    logger.warning(
                        "Subscription has no topics: domain=%s spec=%s",
                        domain.name,
                        spec.id,
                    )
                    continue

                broker_name = self._broker_name(spec)
                qos = self._qos(spec)
                broker_name = self._broker_name(spec) or "<default>"

                handler = self._wrap_handler(
                    domain=domain, spec=spec, broker_name=broker_name
                )

                res: SubscribeResult = await self._broker_service.subscribe(
                    topics=topics,
                    handler=handler,
                    broker_name=broker_name,
                    qos=qos,
                )

                if not res.success or not res.subscription_id:
                    logger.warning(
                        "Subscribe failed: domain=%s spec=%s topics=%s error=%s",
                        domain.name,
                        spec.id,
                        topics,
                        res.error,
                    )
                    continue

                self._active.append(
                    ActiveSubscription(
                        domain_name=domain.name,
                        spec_id=spec.id,
                        topics=topics,
                        subscription_id=res.subscription_id,
                        broker_name=broker_name,
                    )
                )
                logger.info(
                    "Subscribed: domain=%s spec=%s id=%s broker=%s topics=%s",
                    domain.name,
                    spec.id,
                    res.subscription_id,
                    broker_name or "<default>",
                    topics,
                )

    async def stop(self) -> None:
        for sub in list(self._active):
            try:
                await self._broker_service.unsubscribe(
                    subscription_id=sub.subscription_id,
                    broker_name=sub.broker_name,
                )
            except Exception:
                logger.exception(
                    "Unsubscribe failed: domain=%s spec=%s sub_id=%s",
                    sub.domain_name,
                    sub.spec_id,
                    sub.subscription_id,
                )
        self._active.clear()

    def _broker_name(self, spec: SubscriptionSpec) -> str | None:
        # Optional metadata override
        broker_name = spec.metadata.get("broker")
        if isinstance(broker_name, str) and broker_name.strip():
            return broker_name.strip()
        return self._default_broker_name

    def _qos(self, spec: SubscriptionSpec) -> QoS:
        # Optional metadata override; supports "0|1|2" or "AT_LEAST_ONCE" etc.
        qos = spec.metadata.get("qos")
        if isinstance(qos, QoS):
            return qos
        if isinstance(qos, int):
            try:
                return QoS(qos)
            except Exception:
                return self._default_qos
        if isinstance(qos, str):
            q = qos.strip().upper()
            if q.isdigit():
                try:
                    return QoS(int(q))
                except Exception:
                    return self._default_qos
            try:
                return QoS[q]
            except Exception:
                return self._default_qos
        return self._default_qos

    def _expand_topics(self, topics: list[str]) -> list[str]:
        # Initial version: no template expansion except pass-through.
        # (If you later support {entity_id}, do it here.)
        return [t for t in topics if isinstance(t, str) and t.strip()]

    def _wrap_handler(
        self,
        domain: DTDomain,
        spec: SubscriptionSpec,
        broker_name: str,
    ) -> Callable[[ReceivedMessage], Awaitable[None]]:
        async def _handler(msg: ReceivedMessage) -> None:
            try:
                event = _dt_event_from_received(domain=domain, spec=spec, msg=msg)
                ctx = _event_context_from_received(
                    spec=spec, msg=msg, broker_name=broker_name
                )
                for h in spec.handlers:
                    try:
                        await h(event, ctx)
                    except Exception:
                        logger.exception(
                            "Subscription handler %s error: domain=%s spec=%s topic=%s",
                            str(h.__name__),
                            domain.name,
                            spec.id,
                            msg.topic,
                        )
            except Exception:
                logger.exception(
                    "Subscription handler error: domain=%s spec=%s topic=%s",
                    domain.name,
                    spec.id,
                    msg.topic,
                )

        return _handler
