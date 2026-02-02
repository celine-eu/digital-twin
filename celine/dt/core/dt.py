# celine/dt/core/dt.py
"""
Digital Twin runtime core with event broker and subscription support.

This module provides the central DT class that orchestrates app execution,
values fetching, state management, event publishing, and event subscription.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, TYPE_CHECKING

from celine.dt.core.utils import utc_now

from celine.dt.core.broker.service import BrokerService, NullBrokerService
from celine.dt.core.simulation.run_service import RunService
from celine.dt.core.simulation.runner import SimulationRunner
from celine.dt.core.simulation.scenario import ScenarioService

# avoid dependency loop
if TYPE_CHECKING:
    from celine.dt.core.registry import DTRegistry
    from celine.dt.core.runner import DTAppRunner
    from celine.dt.core.state import StateStore
    from celine.dt.core.auth.provider import TokenProvider
    from celine.dt.core.values.service import ValuesService
    from celine.dt.core.broker.service import BrokerService
    from celine.dt.core.subscription.service import SubscriptionService
    from celine.dt.core.context import RunContext

logger = logging.getLogger(__name__)


class DT:
    """Digital Twin runtime core.

    This object is transport-agnostic. API layers (FastAPI or others) should act as
    thin gates that delegate to this runtime.

    The DT instance is intended to be application-scoped.
    Request-scoped attributes (request_id, now, auth context, etc.) are carried by
    a per-invocation RunContext which is a lightweight shim inheriting from DT.

    Attributes:
        registry: Registry of DT apps and modules.
        runner: App execution engine.
        values: Service for fetching data values.
        state: Persistent state store for apps.
        token_provider: Optional OIDC token provider.
        broker: Optional event broker service for publishing events.
        subscriptions: Optional subscription service for receiving events.
        services: Additional injectable services.
    """

    def __init__(
        self,
        *,
        registry: "DTRegistry",
        runner: "DTAppRunner",
        values: "ValuesService",
        state: "StateStore",
        token_provider: "TokenProvider | None" = None,
        broker: "BrokerService | None" = None,
        subscriptions: "SubscriptionService | None" = None,
        services: Mapping[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner
        self.values = values
        self.state = state
        self.token_provider = token_provider
        self.broker: BrokerService = broker or NullBrokerService()
        self.subscriptions = subscriptions
        self.services = dict(services) if services else {}

        # Simulation subsystem (wired by main.py / API layer)
        self.simulations: Any | None = None
        self.scenario_service: ScenarioService | None = None
        self.run_service: RunService | None = None
        self.simulation_runner: SimulationRunner | None = None

    # ---------------------------------------------------------------------
    # Apps
    # ---------------------------------------------------------------------

    def list_apps(self) -> list[dict[str, Any]]:
        return self.registry.list_apps()

    def describe_app(self, app_key: str) -> dict[str, Any]:
        return self.registry.describe_app(app_key)

    async def run_app(
        self,
        *,
        app_key: str,
        payload: Mapping[str, Any] | None,
        context: Any,
    ) -> Any:
        """Execute a registered app."""
        return await self.runner.run(
            registry=self.registry,
            app_key=app_key,
            payload=payload,
            context=context,
        )

    # ---------------------------------------------------------------------
    # Context
    # ---------------------------------------------------------------------

    def create_context(
        self,
        *,
        request: Any | None = None,
        request_scope: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> "RunContext":
        from celine.dt.core.context import RunContext  # local import to avoid cycles

        return RunContext.from_dt(
            self,
            request=request,
            request_scope=request_scope,
            request_id=request_id,
            now=now or utc_now(),
        )

    # ---------------------------------------------------------------------
    # Broker convenience methods (publishing)
    # ---------------------------------------------------------------------

    def has_broker(self) -> bool:
        """Check if a broker service is configured."""
        return self.broker is not None and self.broker.has_brokers()

    async def publish_event(
        self,
        event: Any,
        topic: str | None = None,
        broker_name: str | None = None,
    ) -> Any:
        """
        Publish an event via the broker service.

        This is a convenience method that delegates to the broker service.
        If no broker is configured, logs a warning and returns a failure result.

        Args:
            event: Event to publish (typically a Pydantic model).
            topic: Optional topic override.
            broker_name: Optional specific broker to use.

        Returns:
            PublishResult from the broker, or a failure result if no broker.
        """
        if not self.has_broker() or self.broker is None:
            logger.debug("No broker configured, event not published")
            from celine.dt.contracts.broker import PublishResult

            return PublishResult(success=False, error="No broker configured")

        return await self.broker.publish_event(
            event=event,
            topic=topic,
            broker_name=broker_name,
        )

    # ---------------------------------------------------------------------
    # Subscription convenience methods (receiving)
    # ---------------------------------------------------------------------

    def has_subscriptions(self) -> bool:
        """Check if a subscription service is configured."""
        return self.subscriptions is not None

    async def subscribe(
        self,
        topics: list[str],
        handler: Any,
        subscription_id: str | None = None,
    ) -> str | None:
        """
        Subscribe to events on the given topics.

        This is a convenience method that delegates to the subscription service.

        Args:
            topics: List of topic patterns.
            handler: Async function to call when events match.
            subscription_id: Optional custom ID.

        Returns:
            The subscription ID, or None if no subscription service.
        """
        if not self.has_subscriptions() or self.subscriptions is None:
            logger.debug("No subscription service configured")
            return None

        return await self.subscriptions.subscribe(
            topics=topics,
            handler=handler,
            subscription_id=subscription_id,
        )

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from events.

        Args:
            subscription_id: The subscription ID to remove.

        Returns:
            True if found and removed, False otherwise.
        """
        if not self.has_subscriptions() or self.subscriptions is None:
            return False

        return await self.subscriptions.unsubscribe(subscription_id)

    def get_component(self, key: str) -> Any:
        return self.registry.get_component(key)
