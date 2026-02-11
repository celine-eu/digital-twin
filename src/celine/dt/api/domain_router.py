# celine/dt/api/domain_router.py
"""Build router for a domain with autodiscovered routes."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter

from celine.dt.core.router_discovery import discover

if TYPE_CHECKING:
    from celine.dt.core.domain.base import DTDomain

log = logging.getLogger(__name__)


def build_router(domain: "DTDomain") -> APIRouter:
    """
    Build complete router for domain.

    Discovers routes from domain's routes/ package and mounts them
    under /{entity_id_param}/.
    """
    router = APIRouter(tags=[domain.name])
    ep = domain.entity_id_param

    for fr in discover(domain):
        # Mount at /{entity_id}/prefix/...
        prefix = f"/{{{ep}}}{fr.prefix}" if fr.prefix else f"/{{{ep}}}"

        router.include_router(
            fr.router,
            prefix=prefix,
            tags=fr.tags or [domain.name],
        )

        log.info("Mounted %s at %s%s", fr.name, domain.route_prefix, prefix)

    return router
