# celine/dt/core/infrastructure.py
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from celine.dt.core.broker.service import BrokerService
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.values.service import ValuesService, ValuesRegistry
from celine.dt.core.simulation.registry import SimulationRegistry

if TYPE_CHECKING:
    from celine.dt.core.domain.registry import DomainRegistry
    from celine.dt.core.broker.subscriptions import SubscriptionManager
    from celine.sdk.auth import TokenProvider


@dataclass
class Infrastructure:

    # always present after create_app
    broker: BrokerService
    values_service: ValuesService
    values_registry: ValuesRegistry
    clients_registry: ClientsRegistry
    simulation_registry: SimulationRegistry

    # set after lifespan finalization
    _domain_registry: Optional[DomainRegistry] = field(default=None)
    _subscription_manager: Optional[SubscriptionManager] = field(default=None)
    _token_provider: Optional[TokenProvider] = field(default=None)

    overrides: dict[str, Any] = field(default_factory=dict)
   
    @property
    def domain_registry(self) -> DomainRegistry:
        if self._domain_registry is None:
            raise RuntimeError("Infrastructure.domains not set yet - domain loading incomplete")
        return self._domain_registry

    @property
    def subscription_manager(self) -> SubscriptionManager:
        if self._subscription_manager is None:
            raise RuntimeError("Infrastructure.subscription_manager not set yet - lifespan incomplete")
        return self._subscription_manager

    @property
    def token_provider(self) -> TokenProvider:
        if self._token_provider is None:
            raise RuntimeError("Infrastructure.token_provider not set yet - lifespan incomplete")
        return self._token_provider

    def with_overrides(self, overrides: dict[str, Any]) -> Infrastructure:
        """Return a shallow copy with domain-specific overrides applied."""
        return replace(self, overrides=overrides)