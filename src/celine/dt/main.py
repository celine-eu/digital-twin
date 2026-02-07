# celine/dt/main.py
"""
Digital Twin application factory.

Creates a FastAPI application with domain-driven routing.
Each domain is mounted under its own prefix with auto-generated
routes for values, simulations, and custom endpoints.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from celine.dt.api.discovery import router as discovery_router
from celine.dt.api.domain_router import build_domain_router
from celine.dt.core.broker.service import BrokerService, NullBrokerService
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.config import settings
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.config import load_domains_config
from celine.dt.core.domain.loader import load_and_register_domains
from celine.dt.core.domain.registry import DomainRegistry
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.core.values.executor import FetcherDescriptor, ValuesFetcher
from celine.dt.core.values.service import ValuesRegistry, ValuesService
from celine.dt.core.clients.loader import load_and_register_clients

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    import sys

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
    """Register a domain's value fetchers into the global values registry.

    Fetcher IDs are namespaced as ``{domain.name}.{fetcher_id}``.
    """
    for spec in domain.get_value_specs():
        ns_id = f"{domain.name}.{spec.id}"
        if not clients_registry.has(spec.client):
            raise KeyError(
                f"Domain '{domain.name}' fetcher '{spec.id}' references "
                f"unknown client '{spec.client}'. Available: {clients_registry.list()}"
            )
        client = clients_registry.get(spec.client)

        # TODO: resolve output_mapper via import_attr if spec.output_mapper is set
        from dataclasses import replace

        ns_spec = replace(spec, id=ns_id)
        descriptor = FetcherDescriptor(spec=ns_spec, client=client)
        values_registry.register(descriptor)


def _register_domain_simulations(
    domain: DTDomain,
    simulation_registry: SimulationRegistry,
) -> None:
    """Register a domain's simulations into the global simulation registry.

    Simulation keys are expected to already be namespaced by the domain
    implementation (e.g. ``it-energy-community.rec-planning``).
    """
    for sim in domain.get_simulations():
        simulation_registry.register(sim)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect brokers, start domains, then shutdown."""
    broker: BrokerService = app.state.broker_service
    domain_registry: DomainRegistry = app.state.domain_registry

    # Connect brokers
    if broker.has_brokers():
        logger.info("Connecting brokers...")
        results = await broker.connect_all()
        for name, ok in results.items():
            lvl = logging.INFO if ok else logging.WARNING
            logger.log(lvl, "Broker '%s': %s", name, "connected" if ok else "FAILED")

    # Start domains
    for domain in domain_registry:
        try:
            await domain.on_startup()
            logger.info("Domain '%s' started", domain.name)
        except Exception:
            logger.exception("Domain '%s' startup failed", domain.name)

    yield

    # Shutdown domains
    for domain in domain_registry:
        try:
            await domain.on_shutdown()
        except Exception:
            logger.exception("Domain '%s' shutdown failed", domain.name)

    # Disconnect brokers
    if broker.has_brokers():
        logger.info("Disconnecting brokers...")
        await broker.disconnect_all()


def create_app() -> FastAPI:
    """Build the Digital Twin FastAPI application."""
    _configure_logging(settings.log_level)
    logger.info("Creating DT application (env=%s)", settings.app_env)

    # ------------------------------------------------------------------
    # 1. Shared infrastructure
    # ------------------------------------------------------------------
    clients_registry = ClientsRegistry()
    # In production, clients are loaded from config/clients.yaml.
    # For now the registry is empty; domains that need clients should
    # ensure they're registered before use.

    broker_service: BrokerService = NullBrokerService()
    # In production, brokers are loaded from config/brokers.yaml.

    values_registry = ValuesRegistry()
    values_fetcher = ValuesFetcher()
    values_service = ValuesService(registry=values_registry, fetcher=values_fetcher)

    simulation_registry = SimulationRegistry()

    infrastructure = {
        "clients_registry": clients_registry,
        "broker_service": broker_service,
        "values_service": values_service,
        "simulation_registry": simulation_registry,
    }

    # ------------------------------------------------------------------
    # 2.1. Load and register clients
    # ------------------------------------------------------------------
    try:
        load_and_register_clients(
            patterns=settings.clients_config_paths,
            registry=clients_registry,
            token_provider=None,  # wire OIDC provider here when ready
        )
    except FileNotFoundError:
        logger.warning("No clients config found, starting with empty clients registry")

    # ------------------------------------------------------------------
    # 2.2. Load and register domains
    # ------------------------------------------------------------------
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

    # Wire domain capabilities into shared registries
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

    # ------------------------------------------------------------------
    # 3. Build FastAPI application
    # ------------------------------------------------------------------
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

    # Mount discovery routes
    app.include_router(discovery_router)

    # Mount per-domain routers
    for domain in domain_registry:
        domain_router = build_domain_router(
            domain,
            values_service=values_service,
            simulation_registry=simulation_registry,
        )
        app.include_router(
            domain_router,
            prefix=domain.route_prefix,
        )
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
