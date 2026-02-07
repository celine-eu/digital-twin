# celine/dt/api/domain_router.py
"""
Domain router factory.

For each registered DTDomain, this module builds a FastAPI router that:
1. Extracts the entity ID from the URL path.
2. Calls ``domain.resolve_entity()`` (returns 404 on failure).
3. Mounts auto-generated sub-routes for ``/values/...`` and ``/simulations/...``.
4. Mounts the domain's custom router (if any).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValuesRequest
from celine.dt.core.context import RunContext
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.values.service import ValuesService
from celine.dt.core.simulation.registry import SimulationRegistry

logger = logging.getLogger(__name__)


def build_domain_router(
    domain: DTDomain,
    *,
    values_service: ValuesService,
    simulation_registry: SimulationRegistry,
) -> APIRouter:
    """Build a complete router for a domain.

    The router is mounted at ``/{domain.route_prefix}`` by the application.

    URL structure::

        /{prefix}/{entity_id}/values
        /{prefix}/{entity_id}/values/{fetcher_id}
        /{prefix}/{entity_id}/values/{fetcher_id}/describe
        /{prefix}/{entity_id}/simulations
        /{prefix}/{entity_id}/simulations/{sim_key}/describe
        /{prefix}/{entity_id}/...custom routes...
    """
    entity_param = domain.entity_id_param
    router = APIRouter(tags=[domain.name])

    # -- helpers ---------------------------------------------------------

    async def _resolve(domain: DTDomain, entity_id: str) -> EntityInfo:
        """Resolve entity or raise 404."""
        entity = await domain.resolve_entity(entity_id)
        if entity is None:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{entity_id}' not found in domain '{domain.name}'",
            )
        return entity

    def _make_context(
        request: Request,
        entity: EntityInfo,
        values_svc: ValuesService,
    ) -> RunContext:
        broker_svc = getattr(request.app.state, "broker_service", None)
        services = {}
        clients_reg = getattr(request.app.state, "clients_registry", None)
        if clients_reg:
            services["clients_registry"] = clients_reg
        return RunContext(
            entity=entity,
            values_service=values_svc,
            broker_service=broker_svc,
            services=services,
        )

    # -- domain discovery ------------------------------------------------

    @router.get(f"/{{{entity_param}}}")
    async def domain_info(request: Request, **path_params: Any) -> dict:
        """Describe available capabilities for this entity."""
        eid = path_params[entity_param]
        entity = await _resolve(domain, eid)
        return {
            "entity_id": entity.id,
            "domain": domain.name,
            "domain_type": domain.domain_type,
            "values": [v.id for v in domain.get_value_specs()],
            "simulations": [s.key for s in domain.get_simulations()],
        }

    # -- values sub-routes -----------------------------------------------

    values_prefix = f"/{{{entity_param}}}/values"

    @router.get(values_prefix)
    async def list_values(request: Request, **path_params: Any) -> list[dict]:
        eid = path_params[entity_param]
        await _resolve(domain, eid)
        specs = domain.get_value_specs()
        return [
            {"id": s.id, "client": s.client, "has_payload_schema": s.payload_schema is not None}
            for s in specs
        ]

    @router.get(values_prefix + "/{fetcher_id}/describe")
    async def describe_value(fetcher_id: str, request: Request, **path_params: Any) -> dict:
        eid = path_params[entity_param]
        await _resolve(domain, eid)
        ns_id = f"{domain.name}.{fetcher_id}"
        try:
            return values_service.describe(ns_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")

    @router.get(values_prefix + "/{fetcher_id}")
    async def get_value(
        fetcher_id: str,
        request: Request,
        **path_params: Any,
    ) -> dict:
        eid = path_params[entity_param]
        entity = await _resolve(domain, eid)
        ns_id = f"{domain.name}.{fetcher_id}"

        reserved = {"limit", "offset"}
        params = {k: v for k, v in request.query_params.items() if k not in reserved}
        limit_str = request.query_params.get("limit")
        offset_str = request.query_params.get("offset")
        limit = int(limit_str) if limit_str else None
        offset = int(offset_str) if offset_str else None

        try:
            result = await values_service.fetch(
                fetcher_id=ns_id,
                payload=params,
                entity=entity,
                limit=limit,
                offset=offset,
            )
            return result.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            logger.exception("Fetch failed for '%s'", ns_id)
            raise HTTPException(status_code=500, detail="Fetch operation failed")

    @router.post(values_prefix + "/{fetcher_id}")
    async def post_value(
        fetcher_id: str,
        body: ValuesRequest,
        request: Request,
        **path_params: Any,
    ) -> dict:
        eid = path_params[entity_param]
        entity = await _resolve(domain, eid)
        ns_id = f"{domain.name}.{fetcher_id}"

        limit_str = request.query_params.get("limit")
        offset_str = request.query_params.get("offset")
        limit = int(limit_str) if limit_str else None
        offset = int(offset_str) if offset_str else None

        try:
            result = await values_service.fetch(
                fetcher_id=ns_id,
                payload=body.payload,
                entity=entity,
                limit=limit,
                offset=offset,
            )
            return result.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            logger.exception("Fetch failed for '%s'", ns_id)
            raise HTTPException(status_code=500, detail="Fetch operation failed")

    # -- simulations sub-routes ------------------------------------------

    sims_prefix = f"/{{{entity_param}}}/simulations"

    @router.get(sims_prefix)
    async def list_simulations(request: Request, **path_params: Any) -> list[dict]:
        eid = path_params[entity_param]
        await _resolve(domain, eid)
        sims = domain.get_simulations()
        return [
            {"key": s.key, "version": s.version}
            for s in sims
        ]

    @router.get(sims_prefix + "/{sim_key}/describe")
    async def describe_simulation(sim_key: str, request: Request, **path_params: Any) -> dict:
        eid = path_params[entity_param]
        await _resolve(domain, eid)
        ns_key = f"{domain.name}.{sim_key}"
        try:
            desc = simulation_registry.get(ns_key)
            return desc.describe()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Simulation '{sim_key}' not found")

    # -- mount custom routes ---------------------------------------------

    custom = domain.routes()
    if custom is not None:
        router.include_router(custom, prefix=f"/{{{entity_param}}}")

    return router
