from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from celine.dt.core.config import settings
from celine.dt.core.logging import configure_logging
from celine.dt.core.registry import AppRegistry
from celine.dt.core.ontology import build_ontology_bundle
from celine.dt.db.engine import get_async_engine

from celine.dt.routes import recs, scenarios, runs, admin

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    registry = AppRegistry()
    registry.load_from_yaml(settings.apps_config_path)
    registry.register_enabled_apps()

    # ontology bundle
    app_ttl: list[str] = []
    app_jsonld: list[str] = []
    for a in registry.apps.values():
        app_ttl.extend(a.ontology_ttl_files())
        app_jsonld.extend(a.ontology_jsonld_files())
    bundle = build_ontology_bundle(app_jsonld_files=app_jsonld, app_ttl_files=app_ttl)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.registry = registry
        app.state.jsonld_context_files = bundle.jsonld_context_files
        yield

    app = FastAPI(title="CELINE Digital Twin", version="0.1.0", lifespan=lifespan)

    # include core routers
    app.include_router(recs.router)
    app.include_router(scenarios.router)
    app.include_router(runs.router)
    app.include_router(admin.router)

    # include app routers
    for a in registry.apps.values():
        r = a.router()
        if r:
            app.include_router(r)

    @app.get("/health", tags=["core"])
    async def health() -> dict:
        return {
            "status": "ok",
            "env": settings.app_env,
            "apps": [
                {"key": k, "version": v.version} for k, v in registry.apps.items()
            ],
            "ontology": {
                "ttl_files": bundle.ttl_files,
                "jsonld_context_files": bundle.jsonld_context_files,
            },
        }

    return app
