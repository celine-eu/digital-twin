# celine/dt/core/domain/base.py
"""
DTDomain – the organising abstraction for Digital Twin verticals.

A domain bundles values, simulations, broker subscriptions, and custom
routes into a cohesive, entity-scoped API surface. The DT core mounts
each domain under its ``route_prefix`` and takes care of:

* Entity resolution (with an optional domain-provided callback).
* Jinja-based query templating with automatic entity context injection.
* Auto-generated routes for ``/values/...`` and ``/simulations/...``.
* Broker subscription wiring with ``{entity_id}`` expansion.
"""
from __future__ import annotations

import logging
from abc import ABC
from typing import Any, ClassVar, Sequence

from fastapi import APIRouter, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.simulation import DTSimulation
from celine.dt.contracts.subscription import SubscriptionSpec
from celine.dt.contracts.values import ValueFetcherSpec

logger = logging.getLogger(__name__)


class DTDomain(ABC):
    """Base class for all Digital Twin domains.

    Subclass to create a concrete domain type (e.g. ``EnergyCommunityDomain``).
    Then subclass *that* for locale/regulatory variants.

    Class attributes
    ~~~~~~~~~~~~~~~~
    name
        Machine-readable identifier (e.g. ``"it-energy-community"``).
    domain_type
        Shared type across locale variants (e.g. ``"energy-community"``).
    version
        Semantic version of this domain implementation.
    route_prefix
        URL path prefix **without** trailing slash (e.g. ``"/communities"``).
    entity_id_param
        Path parameter name for the entity (e.g. ``"community_id"``).

    Override points
    ~~~~~~~~~~~~~~~
    * ``get_value_specs`` – return value fetcher definitions.
    * ``get_simulations`` – return simulation instances.
    * ``get_subscriptions`` – return broker subscription specs.
    * ``routes`` – return a FastAPI router with custom endpoints.
    * ``resolve_entity`` – validate/enrich the entity from the URL.
    * ``on_startup`` / ``on_shutdown`` – lifecycle hooks.
    """

    # -- identity (override in subclass) -------------------------------------
    name: ClassVar[str]
    domain_type: ClassVar[str]
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str]
    entity_id_param: ClassVar[str]

    # -- infrastructure (injected by the runtime at registration) ------------
    _infrastructure: dict[str, Any]

    def __init__(self) -> None:
        self._infrastructure = {}

    def set_infrastructure(self, infra: dict[str, Any]) -> None:
        """Called by the runtime during domain registration.

        Provides shared services: ``values_service``, ``broker_service``,
        ``clients_registry``, ``token_provider``, etc.
        """
        self._infrastructure = infra

    @property
    def infra(self) -> dict[str, Any]:
        return self._infrastructure

    # -- capabilities --------------------------------------------------------

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        """Return value fetcher definitions for this domain.

        Override in subclass. Default: no fetchers.
        """
        return []

    def get_simulations(self) -> list[DTSimulation]:  # type: ignore[type-arg]
        """Return simulation instances for this domain.

        Override in subclass. Default: no simulations.
        """
        return []

    def get_subscriptions(self) -> list[SubscriptionSpec]:
        """Return broker subscription specs.

        Override in subclass. Topic patterns may include ``{entity_id}``
        which will be expanded by the subscription manager.
        """
        return []

    def routes(self) -> APIRouter | None:
        """Return a FastAPI router with domain-specific custom endpoints.

        Override in subclass. Return ``None`` if no custom routes needed.
        The router will be mounted at
        ``/{route_prefix}/{entity_id_param}/``.
        """
        return None

    # -- entity resolution ---------------------------------------------------

    async def resolve_entity(
        self, entity_id: str, request: Request
    ) -> EntityInfo | None:
        """Validate and optionally enrich an entity from the URL path.

        Override to add validation (return ``None`` to reject → 404)
        or to populate ``EntityInfo.metadata`` with data that should be
        available in Jinja query templates and handler context.

        Default implementation: passthrough – always valid, no extra metadata.
        """
        return EntityInfo(id=entity_id, domain_name=self.name)

    # -- lifecycle -----------------------------------------------------------

    async def on_startup(self) -> None:
        """Called once after the domain is registered and infrastructure
        is available. Use for one-time initialisation."""
        pass

    async def on_shutdown(self) -> None:
        """Called during application shutdown. Use for cleanup."""
        pass

    # -- introspection -------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Machine-readable description for discovery endpoints."""
        sims = self.get_simulations()
        values = self.get_value_specs()
        subs = self.get_subscriptions()
        return {
            "name": self.name,
            "domain_type": self.domain_type,
            "version": self.version,
            "route_prefix": self.route_prefix,
            "entity_id_param": self.entity_id_param,
            "values": [v.id for v in values],
            "simulations": [s.key for s in sims],
            "subscriptions": len(subs),
            "has_custom_routes": self.routes() is not None,
        }
