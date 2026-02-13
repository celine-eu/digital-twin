from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, cast
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.routes import (
    ValueDescriptorSchema,
    FetchResultSchema,
    ValuesRequestSchema,
)
from celine.dt.core.domain.base import DTDomain
from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.executor import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/values")


@router.get(
    "",
    response_model=list[ValueDescriptorSchema],
    operation_id="list_values",
)
async def list_values(ctx: Ctx = Depends(get_ctx_auth)) -> list[ValueDescriptorSchema]:
    domain: DTDomain = ctx.domain
    payload = domain.values_service.list()
    return [ValueDescriptorSchema.from_descriptor(d) for d in payload]


@router.get(
    "/{fetcher_id}",
    response_model=FetchResultSchema,
    operation_id="fetch_values_get",
)
async def fetch_values_get(
    fetcher_id: str,
    request: Request,
    ctx: Ctx = Depends(get_ctx_auth),
    limit: int | None = Query(default=None, ge=0),
    offset: int | None = Query(default=None, ge=0),
) -> FetchResultSchema:

    qp = request.query_params

    # Convert to dict[str, Any], preserving repeated keys as lists
    payload: dict[str, Any] = {}
    for k in qp.keys():
        vals = qp.getlist(k)
        payload[k] = vals[0] if len(vals) == 1 else vals

    payload.pop("limit", None)
    payload.pop("offset", None)

    domain: DTDomain = ctx.domain
    values = await domain.values_service.fetch(
        fetcher_id=fetcher_id,
        entity=ctx.entity,
        limit=limit,
        offset=offset,
        payload=payload,
    )
    return FetchResultSchema.from_dataclass(values)


@router.post(
    "/{fetcher_id}",
    response_model=FetchResultSchema,
    operation_id="fetch_values_post",
)
async def fetch_values_post(
    fetcher_id: str,
    body: ValuesRequestSchema,
    ctx: Ctx = Depends(get_ctx_auth),
) -> FetchResultSchema:

    # Convert body to dict (Pydantic v2)
    payload: dict[str, Any] = body.payload.model_dump(exclude_none=True)

    # Extract pagination if present
    limit = payload.get("limit")
    offset = payload.get("offset")

    # Optional: remove from payload
    payload.pop("limit", None)
    payload.pop("offset", None)

    domain: DTDomain = ctx.domain
    entity: EntityInfo = ctx.entity

    try:
        values = await domain.values_service.fetch(
            fetcher_id=f"{entity.domain_name}.{fetcher_id}",
            entity=ctx.entity,
            limit=limit,
            offset=offset,
            payload=payload,
        )
        return FetchResultSchema.from_dataclass(values)
    except ValidationError as e:
        raise HTTPException(400, e.to_dict())
    except Exception as e:
        logger.error(f"fetch_values_post({entity.domain_name}/{entity.id}) Failed: {e}")
        raise HTTPException(500, "Internal server error")


@router.get(
    "/{fetcher_id}/describe",
    response_model=ValueDescriptorSchema,
    operation_id="describe_value",
)
async def describe_value(
    fetcher_id: str,
    ctx: Ctx = Depends(get_ctx_auth),
) -> ValueDescriptorSchema:
    domain: DTDomain = ctx.domain
    entity: EntityInfo = ctx.entity
    descriptor = domain.values_service.get_descriptor(
        fetcher_id=f"{entity.domain_name}.{fetcher_id}"
    )
    return ValueDescriptorSchema.from_descriptor(descriptor)
