# celine/dt/api/domain_router.py
"""Build router for a domain with autodiscovered routes."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Path, Depends
from fastapi.routing import APIRoute

from celine.dt.core.domain.routes import info, summary, values, simulations
from celine.dt.core.router_discovery import discover

if TYPE_CHECKING:
    from celine.dt.core.domain.base import DTDomain

log = logging.getLogger(__name__)


def _entity_path_dep(param_name: str):
    async def _dep(entity_id: str = Path(..., alias=param_name)):
        return entity_id

    return _dep


def _namespace_operation_ids(router, *, domain_name: str) -> None:
    for r in router.routes:
        if isinstance(r, APIRoute):
            # If you explicitly set operation_id somewhere, keep it, but namespace it.
            base = r.operation_id or r.name
            # Make it deterministic and unique.
            r.operation_id = f"{domain_name.replace("-", "_")}__{base}"


def build_router(domain: DTDomain) -> APIRouter:
    root = APIRouter(prefix=domain.route_prefix, tags=[domain.name])

    # This dependency only exists to force OpenAPI to include the path parameter.
    entity_dep = _entity_path_dep(domain.entity_id_param)
    entity_scope = APIRouter(
        prefix=f"/{{{domain.entity_id_param}}}",
        dependencies=[Depends(entity_dep)],
    )

    entity_scope.include_router(info.router)
    entity_scope.include_router(summary.router)
    entity_scope.include_router(values.router)
    entity_scope.include_router(simulations.router)

    for fr in discover(domain):
        entity_scope.include_router(
            fr.router,
            prefix=fr.prefix or "",
            tags=[domain.name],
            dependencies=[Depends(entity_dep)],
        )

    _namespace_operation_ids(entity_scope, domain_name=domain.name)
    root.include_router(entity_scope)

    return root
