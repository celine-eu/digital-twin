from __future__ import annotations
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI

from celine.dt.core.config import settings
from celine.dt.core.logging import configure_logging
from celine.dt.core.registry import DTRegistry
from celine.dt.core.modules.config import load_modules_config
from celine.dt.core.modules.loader import load_and_register_modules
from celine.dt.core.ontologies.celine_bundle import celine_bundle

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    registry = DTRegistry()
    registry.register_ontology_bundle(celine_bundle)

    try:
        cfg = load_modules_config(settings.modules_config_paths)
        load_and_register_modules(registry=registry, cfg=cfg)
    except Exception:
        logger.exception("Failed to initialize DT runtime")
        raise

    app = FastAPI(title="CELINE DT", version="1.0.0", lifespan=lifespan)
    app.state.registry = registry

    return app
