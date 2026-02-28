# celine/dt/main.py
"""
Digital Twin application factory.

Creates a FastAPI application with domain-driven routing. Integrates with
``celine.sdk.auth`` for OIDC token handling (both outgoing client-credentials
and incoming JWT verification) and ``celine.sdk.broker`` for MQTT messaging.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, cast

from fastapi import FastAPI

from celine.dt.api.discovery import router as discovery_router
from celine.dt.api.domain_router import build_router
from celine.dt.core.auth import create_token_provider
from celine.dt.core.broker.loader import load_and_register_brokers
from celine.dt.core.broker.service import BrokerService
from celine.dt.core.broker.subscriptions import SubscriptionManager
from celine.dt.core.broker.scanner import scan_handlers
from celine.dt.core.clients.loader import load_and_register_clients
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.config import settings
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.config import load_domains_config
from celine.dt.core.domain.loader import load_and_register_domains
from celine.dt.core.domain.registry import DomainRegistry
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.core.values.executor import FetcherDescriptor, ValuesFetcher
from celine.dt.core.values.service import ValuesRegistry, ValuesService
from celine.dt.contracts import Infrastructure
from celine.dt.contracts.app import AppState

logger = logging.getLogger(__name__)


# -- Helpers -------------------------------------------------------------------


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )


def _register_domain_values(
    domain: DTDomain,
    values_registry: ValuesRegistry,
    clients_registry: ClientsRegistry,
) -> None:
    """Register a domain's value fetchers, namespaced as ``{domain.name}.{id}``."""
    for spec in domain.get_value_specs():
        ns_id = f"{domain.name}.{spec.id}"
        if not clients_registry.has(spec.client):
            raise KeyError(
                f"Domain '{domain.name}' fetcher '{spec.id}' references "
                f"unknown client '{spec.client}'. Available: {clients_registry.list()}"
            )
        client = clients_registry.get(spec.client)
        ns_spec = replace(spec, id=ns_id)
        values_registry.register(FetcherDescriptor(spec=ns_spec, client=client))


def _register_domain_simulations(
    domain: DTDomain,
    simulation_registry: SimulationRegistry,
) -> None:
    for sim in domain.get_simulations():
        simulation_registry.register(sim)


# -- Lifespan ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async finalization: auth, clients, brokers, domains."""

    state = cast(AppState, app.state)
    infra = state.infra

    clients_registry = infra.clients_registry
    broker = infra.broker
    domain_registry = infra.domain_registry
    values_registry = infra.values_registry
    subscription_manager = infra.subscription_manager

    # 1. Token provider
    token_provider = await create_token_provider(
        base_url=settings.oidc.base_url or None,
        client_id=settings.oidc.client_id or None,
        client_secret=settings.oidc.client_secret or None,
        scope=settings.oidc.scope or None,
        verify_ssl=settings.oidc.verify_ssl,
    )
    infra._token_provider = token_provider

    # 2. Clients — loader handles per-client audience scoping internally
    try:
        load_and_register_clients(
            patterns=settings.clients_config_paths,
            registry=clients_registry,
            token_provider=token_provider,
        )
    except FileNotFoundError:
        logger.warning("No clients config found, starting with empty clients registry")
    except Exception:
        logger.exception("Failed to load clients")
        raise

    # 3. Domain values — depends on clients being registered and authenticated
    for domain in domain_registry:
        try:
            _register_domain_values(domain, values_registry, clients_registry)
        except Exception:
            logger.exception("Failed to register values for domain '%s'", domain.name)
            raise

    # 4. Brokers
    try:
        load_and_register_brokers(
            patterns=settings.brokers_config_paths,
            service=broker,
            token_provider=token_provider,
        )
    except FileNotFoundError:
        logger.warning("No brokers config found")
    except Exception:
        logger.exception("Failed to load brokers")

    if broker.has_brokers():
        logger.info("Connecting brokers...")
        results = await broker.connect_all()
        for name, ok in results.items():
            lvl = logging.INFO if ok else logging.WARNING
            logger.log(lvl, "Broker '%s': %s", name, "connected" if ok else "FAILED")

    # 5. Subscriptions and domain startup
    if subscription_manager:
        await subscription_manager.start()

    for domain in domain_registry:
        try:
            await domain.on_startup()
            logger.info("Domain '%s' started", domain.name)
        except Exception:
            logger.exception("Domain '%s' startup failed", domain.name)

    yield

    # Shutdown
    for domain in domain_registry:
        try:
            await domain.on_shutdown()
        except Exception:
            logger.exception("Domain '%s' shutdown error", domain.name)

    if subscription_manager:
        await subscription_manager.stop()

    if broker.has_brokers():
        logger.info("Disconnecting brokers...")
        await broker.disconnect_all()


# -- Application factory -------------------------------------------------------


def create_app() -> FastAPI:
    """Build and wire the Digital Twin FastAPI application."""
    _configure_logging(settings.log_level)
    logger.info("Creating DT application (env=%s)", settings.app_env)

    # 1. Core services
    clients_registry = ClientsRegistry()
    broker_service = BrokerService()
    values_registry = ValuesRegistry()
    values_service = ValuesService(
        registry=values_registry,
        fetcher=ValuesFetcher(),
    )
    simulation_registry = SimulationRegistry()

    infra = Infrastructure(
        broker=broker_service,
        values_service=values_service,
        values_registry=values_registry,
        clients_registry=clients_registry,
        simulation_registry=simulation_registry,
    )

    try:
        domains_cfg = load_domains_config(settings.domains_config_paths)
        domain_registry = load_and_register_domains(
            cfg=domains_cfg,
            infrastructure=infra,
        )
    except FileNotFoundError:
        logger.warning("No domains config found, starting with empty domain registry")
        domain_registry = DomainRegistry()
    except Exception:
        logger.exception("Failed to load domains")
        raise

    infra._domain_registry = domain_registry

    # Simulations have no client dependency — safe to register now
    for domain in domain_registry:
        try:
            _register_domain_simulations(domain, simulation_registry)
        except Exception:
            logger.exception(
                "Failed to register simulations for domain '%s'", domain.name
            )
            raise

    # Values deferred to lifespan — requires clients loaded and authenticated

    # 3. Subscription handlers
    handler_specs = scan_handlers(
        domain_registry=domain_registry,
        extra_packages=[
            # "celine.dt.my_events"
        ],
    )

    subscription_manager = SubscriptionManager(
        infra=infra,
        domains=list(domain_registry),
        handler_specs=handler_specs,
    )
    infra._subscription_manager = subscription_manager

    # 4. FastAPI app
    app = FastAPI(
        title="CELINE Digital Twin",
        version="2.0.0",
        description="Domain-driven Digital Twin runtime",
        lifespan=lifespan,
    )

    app.state.infra = infra

    app.include_router(discovery_router)

    for domain in domain_registry:
        app.include_router(build_router(domain))
        logger.info(
            "Mounted domain '%s' at %s/{%s}/...",
            domain.name,
            domain.route_prefix,
            domain.entity_id_param,
        )

    logger.info(
        "DT application ready: %d domain(s), %d simulation(s) — values and clients finalized in lifespan",
        len(domain_registry),
        len(simulation_registry),
    )

    return app
