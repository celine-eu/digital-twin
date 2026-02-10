# celine/dt/api/domain_router.py
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValuesRequest
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.values.service import ValuesService
from celine.dt.core.simulation.registry import SimulationRegistry

logger = logging.getLogger(__name__)


async def _resolve_entity(
    domain: DTDomain, entity_id: str, request: Request
) -> EntityInfo:
    entity = await domain.resolve_entity(entity_id, request)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found in domain '{domain.name}'",
        )
    return entity


def _op_id(domain_name: str, suffix: str) -> str:
    return f"{domain_name.replace('-', '_')}_{suffix}"


def _int_or_none(val: str | None) -> int | None:
    return int(val) if val else None


async def _fetch_value(
    svc: ValuesService,
    ns_id: str,
    payload: dict,
    entity: EntityInfo,
    fetcher_id: str,
    limit: int | None,
    offset: int | None,
) -> dict:
    try:
        result = await svc.fetch(
            fetcher_id=ns_id,
            payload=payload,
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


def build_domain_router(
    domain: DTDomain,
    *,
    values_service: ValuesService,
    simulation_registry: SimulationRegistry,
) -> APIRouter:
    ep = domain.entity_id_param
    tag = domain.name
    router = APIRouter(tags=[tag])

    # The entity_id path parameter name is dynamic per domain.
    # We use a fixed function param name and map it via Path(alias=...).
    entity_path = Path(..., alias=ep)

    # -- info ------------------------------------------------------------

    @router.get(f"/{{{ep}}}", operation_id=_op_id(tag, "info"))
    async def info(request: Request, entity_id: str = entity_path) -> dict:
        """Describe available capabilities for this entity."""
        entity = await _resolve_entity(domain, entity_id, request)
        return {
            "entity_id": entity.id,
            "domain": domain.name,
            "domain_type": domain.domain_type,
            "values": [v.id for v in domain.get_value_specs()],
            "simulations": [s.key for s in domain.get_simulations()],
        }

    # -- values: list ----------------------------------------------------

    @router.get(f"/{{{ep}}}/values", operation_id=_op_id(tag, "list_values"))
    async def list_values(request: Request, entity_id: str = entity_path) -> list[dict]:
        """List value fetchers available for this entity."""
        await _resolve_entity(domain, entity_id, request)
        return [
            {
                "id": s.id,
                "client": s.client,
                "has_payload_schema": s.payload_schema is not None,
            }
            for s in domain.get_value_specs()
        ]

    # -- values: describe ------------------------------------------------

    @router.get(
        f"/{{{ep}}}/values/{{fetcher_id}}/describe",
        operation_id=_op_id(tag, "describe_value"),
    )
    async def describe_value(
        request: Request,
        fetcher_id: str,
        entity_id: str = entity_path,
    ) -> dict:
        """Describe a value fetcher's schema and metadata."""
        await _resolve_entity(domain, entity_id, request)
        ns_id = f"{domain.name}.{fetcher_id}"
        try:
            return values_service.describe(ns_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"Fetcher '{fetcher_id}' not found"
            )

    # -- values: GET -----------------------------------------------------

    @router.get(
        f"/{{{ep}}}/values/{{fetcher_id}}", operation_id=_op_id(tag, "get_value")
    )
    async def get_value(
        request: Request,
        fetcher_id: str,
        entity_id: str = entity_path,
    ) -> dict:
        """Fetch a value using query-string parameters as payload."""
        entity = await _resolve_entity(domain, entity_id, request)
        ns_id = f"{domain.name}.{fetcher_id}"
        reserved = {"limit", "offset"}
        params = {k: v for k, v in request.query_params.items() if k not in reserved}
        limit = _int_or_none(request.query_params.get("limit"))
        offset = _int_or_none(request.query_params.get("offset"))
        return await _fetch_value(
            values_service, ns_id, params, entity, fetcher_id, limit, offset
        )

    # -- values: POST ----------------------------------------------------

    @router.post(
        f"/{{{ep}}}/values/{{fetcher_id}}", operation_id=_op_id(tag, "post_value")
    )
    async def post_value(
        request: Request,
        fetcher_id: str,
        body: ValuesRequest,
        entity_id: str = entity_path,
    ) -> dict:
        """Fetch a value using a JSON payload."""
        entity = await _resolve_entity(domain, entity_id, request)
        ns_id = f"{domain.name}.{fetcher_id}"
        limit = _int_or_none(request.query_params.get("limit"))
        offset = _int_or_none(request.query_params.get("offset"))
        return await _fetch_value(
            values_service, ns_id, body.payload, entity, fetcher_id, limit, offset
        )

    # -- simulations: list -----------------------------------------------

    @router.get(f"/{{{ep}}}/simulations", operation_id=_op_id(tag, "list_simulations"))
    async def list_simulations(
        request: Request, entity_id: str = entity_path
    ) -> list[dict]:
        """List simulations available for this entity."""
        await _resolve_entity(domain, entity_id, request)
        return [{"key": s.key, "version": s.version} for s in domain.get_simulations()]

    # -- simulations: describe -------------------------------------------

    @router.get(
        f"/{{{ep}}}/simulations/{{sim_key}}/describe",
        operation_id=_op_id(tag, "describe_simulation"),
    )
    async def describe_simulation(
        request: Request,
        sim_key: str,
        entity_id: str = entity_path,
    ) -> dict:
        """Describe a simulation's parameters and configuration."""
        await _resolve_entity(domain, entity_id, request)
        ns_key = f"{domain.name}.{sim_key}"
        try:
            sim = simulation_registry.get(ns_key)
            return sim.describe()
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"Simulation '{sim_key}' not found"
            )

    # -- custom routes ---------------------------------------------------

    custom = domain.routes()
    if custom is not None:
        router.include_router(custom, prefix=f"/{{{ep}}}")

    return router
