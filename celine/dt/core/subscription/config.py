# celine/dt/core/subscription/config.py
"""
Configuration loading for subscriptions.

Loads subscription definitions from YAML and registers them
with the subscription service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, cast

from celine.dt.contracts.subscription import EventHandler, Subscription
from celine.dt.core.loader import import_attr, load_yaml_files, substitute_env_vars
from celine.dt.core.subscription.service import SubscriptionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubscriptionSpec:
    """
    Specification for a subscription from configuration.

    Attributes:
        id: Unique subscription identifier.
        topics: List of topic patterns to subscribe to.
        handler: Import path to handler function (module:function).
        enabled: Whether this subscription is active.
        metadata: Optional metadata.
    """

    id: str
    topics: list[str]
    handler: str  # Import path
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubscriptionsConfig:
    """
    Container for all subscription specifications.

    Attributes:
        subscriptions: List of subscription specs.
    """

    subscriptions: list[SubscriptionSpec] = field(default_factory=list)


def load_subscriptions_config(patterns: Iterable[str]) -> SubscriptionsConfig:
    """
    Load subscriptions configuration from YAML files.

    Expected YAML structure:
    ```yaml
    subscriptions:
      - id: my-handler
        topics:
          - "dt/ev-charging/#"
          - "dt/alerts/+"
        handler: "mymodule.handlers:handle_event"
        enabled: true
        metadata:
          description: "Handles EV charging events"
    ```

    Args:
        patterns: Glob patterns for YAML config files.

    Returns:
        SubscriptionsConfig with all subscription specifications.

    Raises:
        ValueError: If configuration is invalid.
    """
    yamls = load_yaml_files(patterns)

    specs: list[SubscriptionSpec] = []

    for data in yamls:
        subs = data.get("subscriptions", [])

        for raw in subs:
            if "id" not in raw:
                raise ValueError("Subscription missing required 'id' field")

            if "topics" not in raw:
                raise ValueError(
                    f"Subscription '{raw['id']}' missing required 'topics' field"
                )

            if "handler" not in raw:
                raise ValueError(
                    f"Subscription '{raw['id']}' missing required 'handler' field"
                )

            # Substitute env vars in metadata
            metadata = substitute_env_vars(raw.get("metadata", {}))

            spec = SubscriptionSpec(
                id=raw["id"],
                topics=raw["topics"],
                handler=raw["handler"],
                enabled=raw.get("enabled", True),
                metadata=metadata,
            )
            specs.append(spec)

    logger.info(
        "Loaded %d subscription spec(s): %s",
        len(specs),
        [s.id for s in specs],
    )

    return SubscriptionsConfig(subscriptions=specs)


async def register_subscriptions_from_config(
    service: SubscriptionService,
    config: SubscriptionsConfig,
) -> list[str]:
    """
    Register subscriptions from configuration.

    Imports handlers and registers them with the service.

    Args:
        service: The subscription service.
        config: Subscriptions configuration.

    Returns:
        List of registered subscription IDs.

    Raises:
        ImportError: If a handler cannot be imported.
    """
    registered: list[str] = []

    for spec in config.subscriptions:
        if not spec.enabled:
            logger.info("Skipping disabled subscription: %s", spec.id)
            continue

        # Import handler
        try:
            handler = import_attr(spec.handler)
        except (ImportError, AttributeError) as exc:
            logger.error(
                "Failed to import handler '%s' for subscription '%s': %s",
                spec.handler,
                spec.id,
                exc,
            )
            raise

        # Validate handler is callable
        if not callable(handler):
            raise ValueError(
                f"Handler '{spec.handler}' for subscription '{spec.id}' "
                f"is not callable"
            )

        # Register subscription
        try:
            sub_id = await service.subscribe(
                topics=spec.topics,
                handler=cast(EventHandler, handler),
                subscription_id=spec.id,
                metadata=spec.metadata,
            )
            registered.append(sub_id)

            logger.info(
                "Registered subscription '%s' -> %s",
                spec.id,
                spec.handler,
            )

        except ValueError as exc:
            logger.warning(
                "Failed to register subscription '%s': %s",
                spec.id,
                exc,
            )

    return registered
