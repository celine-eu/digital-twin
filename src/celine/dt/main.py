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
from typing import Any

from fastapi import FastAPI

from celine.dt.api.discovery import router as discovery_router
from celine.dt.api.domain_router import build_router
from celine.dt.core.auth import create_token_provider, parse_jwt_user
from celine.dt.core.broker.loader import load_and_register_brokers
from celine.dt.core.broker.service import BrokerService, NullBrokerService
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

logger = logging.getLogger(__name__)


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
        from dataclasses import replace

        ns_spec = replace(spec, id=ns_id)
        descriptor = FetcherDescriptor(spec=ns_spec, client=client)
        values_registry.register(descriptor)


def _register_domain_simulations(
    domain: DTDomain,
    simulation_registry: SimulationRegistry,
) -> None:
    for sim in domain.get_simulations():
        simulation_registry.register(sim)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create token provider, connect brokers, start domains."""
    broker: BrokerService = app.state.broker_service
    domain_registry: DomainRegistry = app.state.domain_registry

    # ── Token provider (async — needs OIDC discovery) ──────────────
    token_provider = await create_token_provider(
        base_url=settings.oidc_token_base_url or None,
        client_id=settings.oidc_client_id or None,
        client_secret=settings.oidc_client_secret or None,
        scope=settings.oidc_client_scope or None,
    )
    app.state.token_provider = token_provider

    # Inject token provider into clients that accept it
    for name in app.state.clients_registry.list():
        client = app.state.clients_registry.get(name)
        if hasattr(client, "_token_provider") and token_provider:
            client._token_provider = token_provider
            logger.info("Injected token provider into client '%s'", name)

    # ── Brokers (loaded from YAML, with token provider) ────────────
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

    # ── Start domains ──────────────────────────────────────────────
    for domain in domain_registry:
        try:
            await domain.on_startup()
            logger.info("Domain '%s' started", domain.name)
        except Exception:
            logger.exception("Domain '%s' startup failed", domain.name)

    yield

    # ── Shutdown ───────────────────────────────────────────────────
    for domain in domain_registry:
        try:
            await domain.on_shutdown()
        except Exception:
            logger.exception("Domain '%s' shutdown error", domain.name)

    if broker.has_brokers():
        logger.info("Disconnecting brokers...")
        await broker.disconnect_all()


def create_app() -> FastAPI:
    """Build the Digital Twin FastAPI application."""
    _configure_logging(settings.log_level)
    logger.info("Creating DT application (env=%s)", settings.app_env)

    # ── 1. Shared infrastructure (synchronous init) ────────────────
    clients_registry = ClientsRegistry()

    # Load clients from YAML (token provider injected later in lifespan)
    try:
        load_and_register_clients(
            patterns=settings.clients_config_paths,
            registry=clients_registry,
            token_provider=None,
        )
    except FileNotFoundError:
        logger.warning("No clients config found, starting with empty clients registry")
    except Exception:
        logger.exception("Failed to load clients")
        raise

    # Broker service — brokers loaded in lifespan (needs async token provider)
    broker_service = BrokerService()

    values_registry = ValuesRegistry()
    values_fetcher = ValuesFetcher()
    values_service = ValuesService(registry=values_registry, fetcher=values_fetcher)

    simulation_registry = SimulationRegistry()

    infrastructure: dict[str, Any] = {
        "clients_registry": clients_registry,
        "broker_service": broker_service,
        "values_service": values_service,
        "simulation_registry": simulation_registry,
    }

    # ── 2. Load and register domains ───────────────────────────────
    try:
        domains_cfg = load_domains_config(settings.domains_config_paths)
        domain_registry = load_and_register_domains(
            cfg=domains_cfg,
            infrastructure=infrastructure,
        )
    except FileNotFoundError:
        logger.warning("No domains config found, starting with empty domain registry")
        domain_registry = DomainRegistry()
    except Exception:
        logger.exception("Failed to load domains")
        raise

    for domain in domain_registry:
        try:
            _register_domain_values(domain, values_registry, clients_registry)
        except Exception:
            logger.exception("Failed to register values for domain '%s'", domain.name)
            raise

        try:
            _register_domain_simulations(domain, simulation_registry)
        except Exception:
            logger.exception(
                "Failed to register simulations for domain '%s'", domain.name
            )
            raise

    # ── 3. Build FastAPI application ───────────────────────────────
    app = FastAPI(
        title="CELINE Digital Twin",
        version="2.0.0",
        description="Domain-driven Digital Twin runtime",
        lifespan=lifespan,
    )

    # Wire state
    app.state.domain_registry = domain_registry
    app.state.broker_service = broker_service
    app.state.clients_registry = clients_registry
    app.state.values_service = values_service
    app.state.simulation_registry = simulation_registry
    app.state.token_provider = None  # set in lifespan

    # Mount discovery routes
    app.include_router(discovery_router)

    # Mount per-domain routers
    for domain in domain_registry:
        domain_router = build_router(
            domain,
        )
        app.include_router(domain_router)
        logger.info(
            "Mounted domain '%s' at %s/{%s}/...",
            domain.name,
            domain.route_prefix,
            domain.entity_id_param,
        )

    logger.info(
        "DT application ready: %d domain(s), %d value fetcher(s), %d simulation(s)",
        len(domain_registry),
        len(values_registry),
        len(simulation_registry),
    )

    return app
