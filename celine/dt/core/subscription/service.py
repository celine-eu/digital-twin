# celine/dt/core/subscription/service.py
"""
Subscription service for Digital Twin event reception.

The SubscriptionService provides the high-level API for subscribing to events,
managing subscriptions, and coordinating between the registry, dispatcher,
and MQTT subscriber.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Awaitable
from uuid import uuid4

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import (
    EventContext,
    EventHandler,
    Subscription,
    SubscriptionResult,
)
from celine.dt.core.subscription.registry import SubscriptionRegistry
from celine.dt.core.subscription.dispatcher import EventDispatcher
from celine.dt.core.broker.subscriber import MqttSubscriber
from celine.dt.core.broker.mqtt import MqttConfig

logger = logging.getLogger(__name__)


# Global registry for decorator-based subscriptions
_pending_subscriptions: list[Subscription] = []


def subscribe(*topics: str, subscription_id: str | None = None):
    """
    Decorator for registering event handlers.
    
    Handlers decorated with @subscribe are collected and registered
    when the SubscriptionService starts.
    
    Example:
        @subscribe("dt/ev-charging/+/readiness")
        async def handle_readiness(event: DTEvent, context: EventContext):
            print(f"Received: {event.type}")
        
        @subscribe("dt/alerts/#", "dt/errors/#", subscription_id="alert-handler")
        async def handle_alerts(event: DTEvent, context: EventContext):
            print(f"Alert on {context.topic}")
    
    Args:
        *topics: Topic patterns to subscribe to.
        subscription_id: Optional custom subscription ID.
    """
    def decorator(func: EventHandler) -> EventHandler:
        sub = Subscription(
            id=subscription_id or f"decorator-{func.__module__}.{func.__name__}",
            topics=list(topics),
            handler=func,
            metadata={"source": "decorator"},
        )
        _pending_subscriptions.append(sub)
        
        @wraps(func)
        async def wrapper(event: DTEvent, context: EventContext) -> None:
            return await func(event, context)
        
        return wrapper
    
    return decorator


class SubscriptionService:
    """
    High-level service for event subscription management.
    
    Provides:
    - Programmatic subscription registration
    - Dynamic add/remove at runtime
    - Integration with MQTT subscriber
    - Coordination with event dispatcher
    
    Example:
        service = SubscriptionService(
            mqtt_config=MqttConfig(host="localhost"),
            token_provider=oidc_provider,
        )
        
        # Register a handler
        sub_id = await service.subscribe(
            topics=["dt/ev-charging/#"],
            handler=my_handler,
        )
        
        # Start listening
        await service.start()
        
        # Later...
        await service.unsubscribe(sub_id)
        await service.stop()
    """
    
    def __init__(
        self,
        mqtt_config: MqttConfig | None = None,
        token_provider: Any | None = None,
        max_concurrent_handlers: int = 100,
    ) -> None:
        """
        Initialize the subscription service.
        
        Args:
            mqtt_config: MQTT configuration. If None, subscriptions work
                but no external events are received.
            token_provider: Optional TokenProvider for JWT authentication.
            max_concurrent_handlers: Maximum concurrent handler invocations.
        """
        self._registry = SubscriptionRegistry()
        self._dispatcher = EventDispatcher(
            registry=self._registry,
            max_concurrent=max_concurrent_handlers,
        )
        
        self._mqtt_config = mqtt_config
        self._token_provider = token_provider
        self._subscriber: MqttSubscriber | None = None
        
        self._running = False
        self._broker_name = "mqtt_default"
    
    @property
    def registry(self) -> SubscriptionRegistry:
        """Get the subscription registry."""
        return self._registry
    
    @property
    def dispatcher(self) -> EventDispatcher:
        """Get the event dispatcher."""
        return self._dispatcher
    
    @property
    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._running
    
    async def subscribe(
        self,
        topics: list[str],
        handler: EventHandler,
        subscription_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Subscribe to events on the given topics.
        
        Args:
            topics: List of topic patterns (supports MQTT wildcards).
            handler: Async function to call when events match.
            subscription_id: Optional custom ID. Auto-generated if not provided.
            metadata: Optional metadata for the subscription.
            
        Returns:
            The subscription ID.
            
        Raises:
            ValueError: If subscription ID already exists.
        """
        sub = Subscription(
            id=subscription_id or f"sub-{uuid4().hex[:8]}",
            topics=topics,
            handler=handler,
            metadata=metadata or {},
        )
        
        sub_id = self._registry.register(sub)
        
        # If running, update MQTT subscriptions
        if self._running and self._subscriber:
            await self._subscriber.add_topics(topics)
        
        logger.info(
            "Registered subscription '%s' for topics: %s",
            sub_id,
            topics,
        )
        
        return sub_id
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe and remove a subscription.
        
        Args:
            subscription_id: The subscription ID to remove.
            
        Returns:
            True if found and removed, False otherwise.
        """
        sub = self._registry.get(subscription_id)
        if sub is None:
            return False
        
        # Remove from registry
        self._registry.unregister(subscription_id)
        
        # Note: We don't remove MQTT subscriptions since other
        # subscriptions might still need those topics
        
        logger.info("Unsubscribed '%s'", subscription_id)
        
        return True
    
    def list_subscriptions(self) -> list[dict[str, Any]]:
        """
        List all subscriptions with their details.
        
        Returns:
            List of subscription info dicts.
        """
        return [
            {
                "id": sub.id,
                "topics": sub.topics,
                "enabled": sub.enabled,
                "metadata": sub.metadata,
            }
            for sub in self._registry.list_all()
        ]
    
    async def start(self) -> None:
        """
        Start the subscription service.
        
        Registers decorator-based subscriptions and starts the MQTT subscriber.
        """
        if self._running:
            logger.warning("Subscription service already running")
            return
        
        # Register pending decorator-based subscriptions
        self._register_pending_subscriptions()
        
        # Start MQTT subscriber if configured
        if self._mqtt_config:
            await self._start_mqtt_subscriber()
        else:
            logger.warning(
                "No MQTT config provided, external events won't be received"
            )
        
        self._running = True
        
        logger.info(
            "Subscription service started with %d subscription(s)",
            len(self._registry),
        )
    
    async def stop(self) -> None:
        """Stop the subscription service."""
        if not self._running:
            return
        
        # Stop MQTT subscriber
        if self._subscriber:
            await self._subscriber.stop()
            self._subscriber = None
        
        self._running = False
        
        logger.info("Subscription service stopped")
    
    def _register_pending_subscriptions(self) -> None:
        """Register all decorator-based subscriptions."""
        global _pending_subscriptions
        
        for sub in _pending_subscriptions:
            try:
                self._registry.register(sub)
                logger.debug(
                    "Registered decorator subscription '%s'",
                    sub.id,
                )
            except ValueError as exc:
                logger.warning(
                    "Failed to register decorator subscription '%s': %s",
                    sub.id,
                    exc,
                )
        
        # Clear pending list
        _pending_subscriptions = []
    
    async def _start_mqtt_subscriber(self) -> None:
        """Start the MQTT subscriber."""
        if self._mqtt_config is None:
            logger.warning("No MQTT config, cannot start subscriber")
            return
        
        # Collect all topics from registered subscriptions
        topics = list(self._registry.get_all_topics())
        
        if not topics:
            logger.warning("No topics to subscribe to")
            return
        
        self._subscriber = MqttSubscriber(
            config=self._mqtt_config,
            token_provider=self._token_provider,
        )
        
        await self._subscriber.start(
            topics=topics,
            on_message=self._on_mqtt_message,
        )
    
    async def _on_mqtt_message(
        self,
        topic: str,
        payload: dict[str, Any],
        raw_payload: bytes,
    ) -> None:
        """
        Handle incoming MQTT message.
        
        Routes the message through the dispatcher.
        """
        await self._dispatcher.dispatch_raw(
            topic=topic,
            payload=payload,
            broker_name=self._broker_name,
            raw_payload=raw_payload,
        )
    
    async def dispatch_local(
        self,
        event: DTEvent,
        topic: str | None = None,
    ) -> int:
        """
        Dispatch a local event (not from MQTT).
        
        Useful for testing or internal event propagation.
        
        Args:
            event: The event to dispatch.
            topic: Optional topic. If not provided, derives from event type.
            
        Returns:
            Number of handlers invoked.
        """
        if topic is None:
            # Derive topic from event type
            event_type = getattr(event, "type", "unknown")
            topic = event_type.replace(".", "/")
        
        context = EventContext(
            topic=topic,
            broker_name="local",
            received_at=datetime.now(timezone.utc),
        )
        
        return await self._dispatcher.dispatch(event, context)
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get subscription service statistics.
        
        Returns:
            Dict with stats about subscriptions and message processing.
        """
        stats = {
            "running": self._running,
            "subscription_count": len(self._registry),
            "enabled_subscriptions": len(self._registry.list_enabled()),
            "dispatch_count": self._dispatcher.dispatch_count,
            "dispatch_errors": self._dispatcher.error_count,
        }
        
        if self._subscriber:
            stats["mqtt"] = {
                "connected": self._subscriber.is_running,
                "message_count": self._subscriber.message_count,
                "error_count": self._subscriber.error_count,
                "topics": self._subscriber.topics,
            }
        
        return stats


class NullSubscriptionService(SubscriptionService):
    """
    No-op subscription service for testing or when subscriptions are disabled.
    """
    
    def __init__(self) -> None:
        super().__init__(mqtt_config=None)
    
    async def start(self) -> None:
        self._running = True
        logger.debug("NullSubscriptionService started (no-op)")
    
    async def stop(self) -> None:
        self._running = False
        logger.debug("NullSubscriptionService stopped (no-op)")
