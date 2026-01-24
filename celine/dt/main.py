from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from celine.dt.api.apps import router as apps_router
from celine.dt.api.values import router as values_router
from celine.dt.core.auth.oidc import OidcClientCredentialsProvider
from celine.dt.core.config import settings
from celine.dt.core.dt import DT
from celine.dt.core.logging import configure_logging
from celine.dt.core.modules.config import load_modules_config
from celine.dt.core.modules.loader import load_and_register_modules
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import get_state_store
from celine.dt.core.clients import load_clients_config, load_and_register_clients
from celine.dt.core.values import (
    load_values_config,
    load_and_register_values,
    ValuesFetcher,
    ValuesService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


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
    # 5. Instantiate DT core (application-scoped)
    # -------------------------------------------------------------------------
    values_fetcher = ValuesFetcher()
    values_service = ValuesService(registry=values_registry, fetcher=values_fetcher)

    dt = DT(
        registry=registry,
        runner=runner,
        values=values_service,
        state=get_state_store(settings.state_store),
        token_provider=token_provider,
        services={"clients_registry": clients_registry},
    )

    # -------------------------------------------------------------------------
    # 6. Create FastAPI app
    # -------------------------------------------------------------------------
    app = FastAPI(
        title="CELINE DT",
        version="1.0.0",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # 7. Wire state (single DT entrypoint)
    # -------------------------------------------------------------------------
    app.state.dt = dt

    # Optional compatibility wiring for existing integrations/tests.
    app.state.registry = registry
    app.state.runner = runner
    app.state.token_provider = token_provider
    app.state.clients_registry = clients_registry
    app.state.values_registry = values_registry
    app.state.values_fetcher = values_fetcher
    app.state.state_store = dt.state

    for client_name, client_instance in clients_registry.items():
        setattr(app.state, client_name, client_instance)
        logger.debug("Wired client '%s' to app.state", client_name)

    # -------------------------------------------------------------------------
    # 8. Health check
    # -------------------------------------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    # -------------------------------------------------------------------------
    # 9. Routers
    # -------------------------------------------------------------------------
    app.include_router(apps_router, prefix="/apps", tags=["apps"])
    app.include_router(values_router, prefix="/values", tags=["values"])

    logger.info(
        "CELINE DT initialized: %d modules, %d apps, %d clients, %d values",
        len(registry.modules),
        len(registry.apps),
        len(clients_registry),
        len(values_registry),
    )

    return app
