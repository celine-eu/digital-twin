# celine/dt/core/subscription/__init__.py
"""
Subscription infrastructure for Digital Twin event reception.

This module provides:
- SubscriptionService for managing event subscriptions
- SubscriptionRegistry for storing subscriptions
- EventDispatcher for routing events to handlers
- Configuration loading from YAML

Example usage:

    from celine.dt.core.subscription import (
        SubscriptionService,
        subscribe,
        load_subscriptions_config,
        register_subscriptions_from_config,
    )

    # Decorator-based subscription
    @subscribe("dt/ev-charging/#")
    async def handle_ev_events(event, context):
        print(f"Received: {event.type} on {context.topic}")

    # Programmatic subscription
    service = SubscriptionService(
        mqtt_config=MqttConfig(host="localhost"),
        token_provider=oidc_provider,
    )

    sub_id = await service.subscribe(
        topics=["dt/alerts/#"],
        handler=my_alert_handler,
    )

    await service.start()
"""

from celine.dt.core.subscription.registry import SubscriptionRegistry
from celine.dt.core.subscription.dispatcher import EventDispatcher
from celine.dt.core.subscription.service import (
    SubscriptionService,
    NullSubscriptionService,
    subscribe,
)
from celine.dt.core.subscription.config import (
    load_subscriptions_config,
    register_subscriptions_from_config,
    SubscriptionSpec,
    SubscriptionsConfig,
)

__all__ = [
    # Registry
    "SubscriptionRegistry",
    # Dispatcher
    "EventDispatcher",
    # Service
    "SubscriptionService",
    "NullSubscriptionService",
    "subscribe",
    # Config
    "load_subscriptions_config",
    "register_subscriptions_from_config",
    "SubscriptionSpec",
    "SubscriptionsConfig",
]
