# celine/dt/core/subscription/registry.py
"""
Subscription registry for managing event subscriptions.

The registry stores subscriptions and provides efficient lookup
for matching subscriptions when events arrive.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterator

from celine.dt.contracts.subscription import Subscription

logger = logging.getLogger(__name__)


class SubscriptionRegistry:
    """
    Thread-safe registry for event subscriptions.

    Provides:
    - Registration and unregistration of subscriptions
    - Efficient lookup by subscription ID
    - Topic-based matching for event routing

    Example:
        registry = SubscriptionRegistry()

        sub = Subscription(
            topics=["dt/ev-charging/#"],
            handler=my_handler,
        )

        sub_id = registry.register(sub)

        # Find matching subscriptions for an event
        matching = registry.get_matching("dt/ev-charging/rec-folgaria/readiness")
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._lock = threading.RLock()

    def register(self, subscription: Subscription) -> str:
        """
        Register a subscription.

        Args:
            subscription: The subscription to register.

        Returns:
            The subscription ID.

        Raises:
            ValueError: If a subscription with the same ID already exists.
        """
        with self._lock:
            if subscription.id in self._subscriptions:
                raise ValueError(f"Subscription '{subscription.id}' already registered")

            self._subscriptions[subscription.id] = subscription

            logger.info(
                "Registered subscription '%s' for topics: %s",
                subscription.id,
                subscription.topics,
            )

            return subscription.id

    def unregister(self, subscription_id: str) -> bool:
        """
        Unregister a subscription.

        Args:
            subscription_id: The subscription ID to remove.

        Returns:
            True if the subscription was found and removed, False otherwise.
        """
        with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(
                    "Attempted to unregister unknown subscription '%s'",
                    subscription_id,
                )
                return False

            del self._subscriptions[subscription_id]

            logger.info("Unregistered subscription '%s'", subscription_id)

            return True

    def get(self, subscription_id: str) -> Subscription | None:
        """
        Get a subscription by ID.

        Args:
            subscription_id: The subscription ID.

        Returns:
            The subscription, or None if not found.
        """
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def get_matching(self, topic: str) -> list[Subscription]:
        """
        Get all enabled subscriptions matching a topic.

        Args:
            topic: The topic to match against.

        Returns:
            List of matching subscriptions.
        """
        with self._lock:
            matching = [
                sub
                for sub in self._subscriptions.values()
                if sub.enabled and sub.matches_topic(topic)
            ]
            return matching

    def list_all(self) -> list[Subscription]:
        """
        List all registered subscriptions.

        Returns:
            List of all subscriptions (enabled and disabled).
        """
        with self._lock:
            return list(self._subscriptions.values())

    def list_enabled(self) -> list[Subscription]:
        """
        List all enabled subscriptions.

        Returns:
            List of enabled subscriptions.
        """
        with self._lock:
            return [sub for sub in self._subscriptions.values() if sub.enabled]

    def enable(self, subscription_id: str) -> bool:
        """
        Enable a subscription.

        Args:
            subscription_id: The subscription ID.

        Returns:
            True if found and enabled, False otherwise.
        """
        with self._lock:
            sub = self._subscriptions.get(subscription_id)
            if sub is None:
                return False
            sub.enabled = True
            logger.info("Enabled subscription '%s'", subscription_id)
            return True

    def disable(self, subscription_id: str) -> bool:
        """
        Disable a subscription (without removing it).

        Args:
            subscription_id: The subscription ID.

        Returns:
            True if found and disabled, False otherwise.
        """
        with self._lock:
            sub = self._subscriptions.get(subscription_id)
            if sub is None:
                return False
            sub.enabled = False
            logger.info("Disabled subscription '%s'", subscription_id)
            return True

    def get_all_topics(self) -> set[str]:
        """
        Get all unique topic patterns from enabled subscriptions.

        Useful for MQTT subscribe operations.

        Returns:
            Set of topic patterns.
        """
        with self._lock:
            topics: set[str] = set()
            for sub in self._subscriptions.values():
                if sub.enabled:
                    topics.update(sub.topics)
            return topics

    def clear(self) -> int:
        """
        Remove all subscriptions.

        Returns:
            Number of subscriptions removed.
        """
        with self._lock:
            count = len(self._subscriptions)
            self._subscriptions.clear()
            logger.info("Cleared %d subscriptions", count)
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    def __contains__(self, subscription_id: str) -> bool:
        with self._lock:
            return subscription_id in self._subscriptions

    def __iter__(self) -> Iterator[Subscription]:
        with self._lock:
            return iter(list(self._subscriptions.values()))
