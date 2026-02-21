# celine/dt/core/broker/subscriptions.py
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, cast

from pydantic import BaseModel, ConfigDict

from celine.sdk.broker import QoS, ReceivedMessage, SubscribeResult

from celine.dt.contracts import DTEvent, EventSource, EventContext, EventHandler, RouteDef, SubscriptionSpec, Infrastructure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class ActiveSubscription:
    source_name: str
    spec_id: str
    topics: list[str]
    subscription_id: str
    broker_name: str | None


class AnyPayload(BaseModel):
    """Fallback payload wrapper for arbitrary JSON objects."""
    model_config = ConfigDict(extra="allow")


def _collect_routes_from_object(obj: object) -> list[RouteDef]:
    """Collect @on_event routes from a class instance (DTDomain or similar)."""
    routes: list[RouteDef] = []
    for _name, member in inspect.getmembers(obj, predicate=inspect.ismethod):
        route: RouteDef | None = getattr(member, "_dt_route", None)
        if route is None:
            continue
        handler = cast(EventHandler, member)
        routes.append(route.with_handler(handler))
    return routes


def _collect_routes_from_module(module: object) -> list[RouteDef]:
    """Collect @on_event routes from a module (plain functions)."""
    routes: list[RouteDef] = []
    for _name, fn in inspect.getmembers(module, predicate=inspect.isfunction):
        route: RouteDef | None = getattr(fn, "_dt_route", None)
        if route is None:
            continue
        handler = cast(EventHandler, fn)
        routes.append(route.with_handler(handler))
    return routes


def _routes_to_specs(routes: list[RouteDef]) -> list[SubscriptionSpec]:
    """Group routes by (broker, topics, event_type) into SubscriptionSpecs."""
    from collections import OrderedDict
    grouped: OrderedDict[tuple[str | None, tuple[str, ...], str], RouteDef] = OrderedDict()
    for r in routes:
        key = (r.broker, tuple(r.topics), r.event_type)
        if key not in grouped:
            grouped[key] = r
        else:
            existing = grouped[key]
            grouped[key] = RouteDef(
                event_type=existing.event_type,
                topics=existing.topics,
                broker=existing.broker,
                enabled=existing.enabled and r.enabled,
                metadata={**existing.metadata, **r.metadata},
                handlers=[*existing.handlers, *r.handlers],
            )
    return [
        SubscriptionSpec(
            topics=r.topics,
            handlers=r.handlers,
            enabled=r.enabled,
            metadata={"event_type": r.event_type, "broker": r.broker, **(r.metadata or {})},
        )
        for r in grouped.values()
    ]


def _dt_event_from_received(
    *,
    source_name: str,
    spec: SubscriptionSpec,
    msg: ReceivedMessage,
) -> DTEvent[AnyPayload]:
    """Build a DTEvent from a ReceivedMessage.

    Supports:
    1) Native DTEvent JSON ('@type', '@context', 'source', 'payload')
    2) Raw JSON payload — wrapped into a DTEvent
    """
    data = msg.payload if isinstance(msg.payload, dict) else {}

    if "@type" in data or "event_type" in data:
        mapped: dict[str, Any] = dict(data)
        if "@type" in mapped and "event_type" not in mapped:
            mapped["event_type"] = mapped.pop("@type")
        if "@context" in mapped and "context" not in mapped:
            mapped["context"] = mapped.pop("@context")
        if "source" not in mapped or not isinstance(mapped["source"], dict):
            mapped["source"] = {"domain": source_name}
        if "payload" not in mapped:
            mapped["payload"] = {}
        payload_obj = (
            AnyPayload.model_validate(mapped["payload"])
            if isinstance(mapped["payload"], dict)
            else AnyPayload()
        )
        mapped["payload"] = payload_obj
        return DTEvent[AnyPayload].model_validate(mapped)

    event_type = (
        spec.metadata.get("event_type") or spec.metadata.get("event_name") or msg.topic
    )
    source = EventSource(
        domain=spec.metadata.get("source_domain") or source_name,
        entity_id=spec.metadata.get("entity_id"),
        handler=spec.metadata.get("handler"),
        version=spec.metadata.get("version", "unknown"),
    )
    return DTEvent[AnyPayload](
        event_type=str(event_type),
        source=source,
        payload=AnyPayload.model_validate(data),
        metadata={"subscription_id": spec.id, **(spec.metadata or {})},
    )


# ---------------------------------------------------------------------------
# SubscriptionManager
# ---------------------------------------------------------------------------

class SubscriptionManager:
    """Materializes @on_event handlers — from DTDomain instances or plain
    modules/functions — into live broker subscriptions.

    Sources accepted by ``start()``:
    - ``domains``: list of DTDomain (or any object with get_subscriptions())
    - ``modules``: list of Python modules containing @on_event plain functions
    """

    def __init__(
        self,
        *,
        infra: Infrastructure,
        domains: list[Any] | None = None,
        handler_specs: list[SubscriptionSpec] | None = None,
        default_qos: QoS = QoS.AT_LEAST_ONCE,
        default_broker_name: str | None = None,
    ) -> None:
        self._infra = infra
        self._domains = domains or []
        self._handler_specs = handler_specs or []
        self._default_qos = default_qos
        self._default_broker_name = default_broker_name
        self._active: list[ActiveSubscription] = []

    @property
    def infra(self) -> Infrastructure:
        return self._infra

    async def start(self) -> None:
        # Domain instances
        for domain in self._domains:
            if hasattr(domain, "get_subscriptions"):
                specs = domain.get_subscriptions() or []
            else:
                specs = _routes_to_specs(_collect_routes_from_object(domain))
            await self._register_specs(specs, source_name=getattr(domain, "name", repr(domain)))

        # Plain-function specs from package scanner
        if self._handler_specs:
            await self._register_specs(self._handler_specs, source_name="<scanned>")

    async def _register_specs(
        self, specs: list[SubscriptionSpec], source_name: str
    ) -> None:
        for spec in specs:
            if not spec.enabled:
                logger.info("Subscription disabled: source=%s spec=%s", source_name, spec.id)
                continue

            topics = self._expand_topics(spec.topics)
            if not topics:
                logger.warning("Subscription has no topics: source=%s spec=%s", source_name, spec.id)
                continue

            broker_name = self._broker_name(spec)
            qos = self._qos(spec)

            handler = self._wrap_handler(
                source_name=source_name,
                spec=spec,
                broker_name=broker_name or "<default>",
            )

            res: SubscribeResult = await self.infra.broker.subscribe(
                topics=topics,
                handler=handler,
                broker_name=broker_name,
                qos=qos,
            )

            if not res.success or not res.subscription_id:
                logger.warning(
                    "Subscribe failed: source=%s spec=%s topics=%s error=%s",
                    source_name, spec.id, topics, res.error,
                )
                continue

            self._active.append(
                ActiveSubscription(
                    source_name=source_name,
                    spec_id=spec.id,
                    topics=topics,
                    subscription_id=res.subscription_id,
                    broker_name=broker_name,
                )
            )
            logger.info(
                "Subscribed: source=%s spec=%s id=%s broker=%s topics=%s",
                source_name, spec.id, res.subscription_id,
                broker_name or "<default>", topics,
            )

    async def stop(self) -> None:
        for sub in list(self._active):
            try:
                await self.infra.broker.unsubscribe(
                    subscription_id=sub.subscription_id,
                    broker_name=sub.broker_name,
                )
            except Exception:
                logger.exception(
                    "Unsubscribe failed: source=%s spec=%s sub_id=%s",
                    sub.source_name, sub.spec_id, sub.subscription_id,
                )
        self._active.clear()

    def _wrap_handler(
        self,
        source_name: str,
        spec: SubscriptionSpec,
        broker_name: str,
    ) -> Callable[[ReceivedMessage], Awaitable[None]]:
        broker_service = self.infra.broker
        values_service = self.infra.values_service
        domain_registry = self.infra.domain_registry

        async def _handler(msg: ReceivedMessage) -> None:
            try:
                event = _dt_event_from_received(
                    source_name=source_name, spec=spec, msg=msg
                )
                ctx = EventContext(
                    infra=self.infra,
                    topic=msg.topic,
                    broker_name=broker_name,
                    received_at=msg.timestamp or datetime.now(timezone.utc),
                    entity_id=spec.metadata.get("entity_id"),
                    message_id=msg.message_id,
                    raw_payload=msg.raw_payload,
                )
                for h in spec.handlers:
                    try:
                        await h(event, ctx)
                    except Exception:
                        logger.exception(
                            "Handler %s error: source=%s spec=%s topic=%s",
                            getattr(h, "__name__", repr(h)),
                            source_name, spec.id, msg.topic,
                        )
            except Exception:
                logger.exception(
                    "Subscription dispatch error: source=%s spec=%s topic=%s",
                    source_name, spec.id, msg.topic,
                )

        return _handler

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _broker_name(self, spec: SubscriptionSpec) -> str | None:
        broker_name = spec.metadata.get("broker")
        if isinstance(broker_name, str) and broker_name.strip():
            return broker_name.strip()
        return self._default_broker_name

    def _qos(self, spec: SubscriptionSpec) -> QoS:
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
        return [t for t in topics if isinstance(t, str) and t.strip()]