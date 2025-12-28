from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from celine.dt.api.apps import router as apps_router
from celine.dt.core.auth.oidc import OidcClientCredentialsProvider
from celine.dt.core.config import settings
from celine.dt.core.datasets.dataset_api import DatasetSqlApiClient
from celine.dt.core.logging import configure_logging
from celine.dt.core.modules.config import load_modules_config
from celine.dt.core.modules.loader import load_and_register_modules
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import MemoryStateStore, get_state_store

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

    registry = DTRegistry()
    runner = DTAppRunner()

    try:
        cfg = load_modules_config(settings.modules_config_paths)
        load_and_register_modules(registry=registry, cfg=cfg)
    except Exception:
        logger.exception("Failed to initialize DT runtime")
        raise

    app = FastAPI(
        title="CELINE DT",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Explicit wiring
    app.state.registry = registry
    app.state.runner = runner

    token_provider = None
    if settings.oidc_client_id and settings.oidc_token_base_url:
        token_provider = OidcClientCredentialsProvider(
            base_url=settings.oidc_token_base_url,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            scope=settings.oidc_client_scope,
        )

    dataset_client = DatasetSqlApiClient(
        base_url=settings.dataset_api_url,
        token_provider=token_provider,
    )

    app.state.token_provider = token_provider
    app.state.dataset_client = dataset_client
    app.state.state_store = get_state_store(settings.state_store)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(apps_router, prefix="/apps", tags=["apps"])
    return app
