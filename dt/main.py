from __future__ import annotations

import logging
from fastapi import FastAPI

from dt.core.config import settings
from dt.core.logging import configure_logging
from dt.core.db import init_db
from dt.core.registry import AppRegistry
from dt.core.ontology import build_ontology_bundle
from dt.api import recs, scenarios, runs, admin

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    registry = AppRegistry()
    registry.load_from_yaml(settings.apps_config_path)
    registry.register_enabled_apps()

    # Build ontology bundle for runtime JSON-LD context injection
    app_ttl = []
    app_jsonld = []
    for a in registry.apps.values():
        app_ttl.extend(a.ontology_ttl_files())
        app_jsonld.extend(a.ontology_jsonld_files())

    bundle = build_ontology_bundle(app_jsonld_files=app_jsonld, app_ttl_files=app_ttl)

    app = FastAPI(
        title="CELINE DT (Core + Apps)",
        version="0.1.0",
    )

    # init db
    init_db()

    # Wire registry into holders used by routers (simple PoC DI)
    from dt.api.scenarios import AppRegistryHolder as ScnHolder
    from dt.api.runs import AppRegistryHolder as RunHolder

    ScnHolder.registry = registry
    RunHolder.registry = registry
    RunHolder.jsonld_context_files = bundle.jsonld_context_files

    # Include core routers
    app.include_router(recs.router)
    app.include_router(scenarios.router)
    app.include_router(runs.router)
    app.include_router(admin.router)

    # Include app routers
    for a in registry.apps.values():
        app_router = a.router()
        if app_router:
            app.include_router(app_router)

    @app.get("/health", tags=["core"])
    def health() -> dict:
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


if __name__ == "__main__":
    create_app()
