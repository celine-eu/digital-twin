# celine/dt/main.py
"""
Digital Twin FastAPI application with broker support.

This is the updated main.py showing how to integrate the broker service
into the DT runtime.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

from celine.dt.api.apps import router as apps_router
from celine.dt.api.values import router as values_router
from celine.dt.api.simulations import router as simulations_router
from celine.dt.core.auth.oidc import OidcClientCredentialsProvider
from celine.dt.core.config import settings
from celine.dt.core.dt import DT
from celine.dt.core.logging import configure_logging
from celine.dt.core.modules.config import load_modules_config
from celine.dt.core.modules.loader import load_and_register_modules
from celine.dt.core.registry import DTRegistry
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout
from celine.dt.core.simulation.scenario_store import FileScenarioStore
from celine.dt.core.simulation.scenario import ScenarioService
from celine.dt.core.simulation.run_service import FileRunStore, RunService
from celine.dt.core.simulation.runner import SimulationRunner
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import get_state_store
from celine.dt.core.clients import load_clients_config, load_and_register_clients
from celine.dt.core.values import (
    load_values_config,
    load_and_register_values,
    ValuesFetcher,
    ValuesService,
)

# NEW: Import broker infrastructure
from celine.dt.core.broker import (
    load_brokers_config,
    load_and_register_brokers,
    BrokerService,
)
from celine.dt.core.broker.service import NullBrokerService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Manages broker connections on startup/shutdown.
    """
    # Startup: Connect brokers
    dt: DT = app.state.dt
    if dt.has_broker():
        logger.info("Connecting brokers...")
        results = await dt.broker.connect_all()
        for name, success in results.items():
            if success:
                logger.info("Broker '%s' connected", name)
            else:
                logger.warning("Broker '%s' failed to connect", name)

    yield

    # Shutdown: Disconnect brokers
    if dt.has_broker():
        logger.info("Disconnecting brokers...")
        await dt.broker.disconnect_all()


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    if os.getenv("DEBUG_ATTACH") == "1":
        import debugpy

        debugpy.listen(("0.0.0.0", 5679))
        logger.info("Debugger listening on 0.0.0.0:5679")

    # -------------------------------------------------------------------------
    # 1. Token provider (injectable service for clients)
    # -------------------------------------------------------------------------
    token_provider = None
    if settings.oidc_client_id and settings.oidc_token_base_url:
        token_provider = OidcClientCredentialsProvider(
            base_url=settings.oidc_token_base_url,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            scope=settings.oidc_client_scope,
        )
        logger.info("OIDC token provider configured")

    # -------------------------------------------------------------------------
    # 2. Load and register clients
    # -------------------------------------------------------------------------
    try:
        clients_cfg = load_clients_config(settings.clients_config_paths)
        clients_registry = load_and_register_clients(
            cfg=clients_cfg,
            injectable_services={"token_provider": token_provider},
        )
    except Exception:
        logger.exception("Failed to load clients")
        raise

    # -------------------------------------------------------------------------
    # 3. Load and register modules
    # -------------------------------------------------------------------------
    registry = DTRegistry()
    runner = DTAppRunner()

    try:
        modules_cfg = load_modules_config(settings.modules_config_paths)
        load_and_register_modules(registry=registry, cfg=modules_cfg)
    except Exception:
        logger.exception("Failed to initialize DT modules")
        raise

    # -------------------------------------------------------------------------
    # 4. Load and register values
    # -------------------------------------------------------------------------
    try:
        values_cfg = load_values_config(
            patterns=settings.values_config_paths,
            modules_cfg=modules_cfg,
        )
        values_registry = load_and_register_values(
            cfg=values_cfg,
            clients_registry=clients_registry,
        )
    except Exception:
        logger.exception("Failed to load values")
        raise

    # -------------------------------------------------------------------------
    # 5. Load and register brokers (NEW)
    # -------------------------------------------------------------------------
    broker_service: BrokerService | None = None

    if settings.broker_enabled:
        try:
            brokers_cfg = load_brokers_config(settings.brokers_config_paths)
            broker_registry = load_and_register_brokers(brokers_cfg)

            if len(broker_registry) > 0:
                broker_service = BrokerService(registry=broker_registry)
                logger.info(
                    "Broker service configured with %d broker(s)",
                    len(broker_registry),
                )
            else:
                logger.info("No brokers configured, using NullBrokerService")
                broker_service = NullBrokerService()

        except FileNotFoundError:
            logger.info("No broker config found, brokers disabled")
            broker_service = NullBrokerService()
        except Exception:
            logger.exception("Failed to load brokers, using NullBrokerService")
            broker_service = NullBrokerService()
    else:
        logger.info("Brokers disabled via configuration")
        broker_service = NullBrokerService()

    # -------------------------------------------------------------------------
    # 6. Instantiate DT core (application-scoped)
    # -------------------------------------------------------------------------
    values_fetcher = ValuesFetcher()
    values_service = ValuesService(registry=values_registry, fetcher=values_fetcher)

    dt = DT(
        registry=registry,
        runner=runner,
        values=values_service,
        state=get_state_store(settings.state_store),
        token_provider=token_provider,
        broker=broker_service,  # NEW: Add broker service
        services={"clients_registry": clients_registry},
    )

    
    # -------------------------------------------------------------------------
    # 6b. Simulation subsystem (scenarios + runs)
    # -------------------------------------------------------------------------
    layout = SimulationWorkspaceLayout(root=Path(settings.dt_workspace_root))
    scenario_store = FileScenarioStore(layout=layout)
    scenario_service = ScenarioService(store=scenario_store, layout=layout, default_ttl_hours=24)

    run_store = FileRunStore(layout=layout)
    run_service = RunService(store=run_store, layout=layout)

    simulation_runner = SimulationRunner(
        registry=registry.simulations,
        scenario_service=scenario_service,
    )

    # Attach to DT instance for API access (thin gate pattern)
    dt.simulations = registry.simulations
    dt.scenario_service = scenario_service
    dt.run_service = run_service
    dt.simulation_runner = simulation_runner

# -------------------------------------------------------------------------
    # 7. Create FastAPI app
    # -------------------------------------------------------------------------
    app = FastAPI(
        title="CELINE DT",
        version="1.0.0",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # 8. Wire state (single DT entrypoint)
    # -------------------------------------------------------------------------
    app.state.dt = dt

    # Optional compatibility wiring for existing integrations/tests.
    app.state.registry = registry
    app.state.runner = runner
    app.state.token_provider = token_provider
    app.state.clients_registry = clients_registry
    app.state.values_registry = values_registry
    app.state.broker_service = broker_service  # NEW

    # -------------------------------------------------------------------------
    # 9. Include routers
    # -------------------------------------------------------------------------
    app.include_router(apps_router, prefix="/apps", tags=["apps"])
    app.include_router(values_router, prefix="/values", tags=["values"])
    app.include_router(simulations_router, prefix="/simulations", tags=["simulations"])

    @app.get("/health")
    async def health():
        broker_status = "connected" if dt.has_broker() else "not configured"
        return {
            "status": "healthy",
            "broker": broker_status,
        }

    return app


