from __future__ import annotations

from typing import Any, Awaitable, Callable, cast
from fastapi import APIRouter, Depends, HTTPException, Query

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.routes import (
    DescribeResponseSchema,
    ValueDescriptorSchema,
    ValueResponseSchema,
    ValuesRequestSchema,
)

router = APIRouter(prefix="/values")


@router.get(
    "",
    response_model=list[ValueDescriptorSchema],
    operation_id="list_values",
)
async def list_values(ctx: Ctx = Depends(get_ctx_auth)) -> list[ValueDescriptorSchema]:
    # Prefer a domain hook if present
    fn = getattr(ctx.domain, "list_values", None)
    if callable(fn):
        list_values = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        items = await list_values(ctx=ctx)
        return [
            (
                ValueDescriptorSchema.model_validate(i)
                if not isinstance(i, ValueDescriptorSchema)
                else i
            )
            for i in items
        ]
    raise HTTPException(
        501,
        "Domain does not implement list_values",
    )


@router.get(
    "/{fetcher_id}",
    response_model=ValueResponseSchema,
    operation_id="get_value",
)
async def get_value(
    fetcher_id: str,
    ctx: Ctx = Depends(get_ctx_auth),
    # Optional generic filters for time-window use cases; safe even if ignored
    start: str | None = Query(None, description="Optional ISO datetime start"),
    end: str | None = Query(None, description="Optional ISO datetime end"),
    granularity: str | None = Query(
        None, description="Optional granularity (e.g. hourly, daily)"
    ),
) -> ValueResponseSchema:
    # Prefer a domain hook if present
    fn = getattr(ctx.domain, "get_value", None)
    if callable(fn):
        get_value = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await get_value(
            ctx=ctx,
            fetcher_id=fetcher_id,
            start=start,
            end=end,
            granularity=granularity,
        )
        return ValueResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    # Fallback to ValuesService.fetch (your ctx already prefixes domain.name in ctx.fetch_value)
    extra: dict[str, Any] = {}
    if start is not None:
        extra["start"] = start
    if end is not None:
        extra["end"] = end
    if granularity is not None:
        extra["granularity"] = granularity

    payload = await ctx.fetch_value(fetcher_id, payload={}, **extra)
    return ValueResponseSchema(
        payload=payload if isinstance(payload, dict) else {"value": payload}
    )


@router.post(
    "/{fetcher_id}",
    response_model=ValueResponseSchema,
    operation_id="post_value",
)
async def post_value(
    fetcher_id: str,
    body: ValuesRequestSchema,
    ctx: Ctx = Depends(get_ctx_auth),
) -> ValueResponseSchema:
    fn = getattr(ctx.domain, "post_value", None)
    if callable(fn):
        post_value = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await post_value(ctx=ctx, fetcher_id=fetcher_id, payload=body.payload)
        return ValueResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    post_fn = getattr(ctx.values_service, "post", None)
    if callable(post_fn):
        post_ = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await post_(
            domain=ctx.domain.name,
            fetcher_id=fetcher_id,
            entity=ctx.entity,
            payload=body.payload,
        )
        return ValueResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    raise HTTPException(
        501, "Domain does not implement post_value and ValuesService has no post"
    )


@router.get(
    "/{fetcher_id}/describe",
    response_model=DescribeResponseSchema,
    operation_id="describe_value",
)
async def describe_value(
    fetcher_id: str,
    ctx: Ctx = Depends(get_ctx_auth),
) -> DescribeResponseSchema:
    fn = getattr(ctx.domain, "describe_value", None)
    if callable(fn):
        describe_value = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await describe_value(ctx=ctx, fetcher_id=fetcher_id)
        return DescribeResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    desc_fn = getattr(ctx.values_service, "describe", None)
    if callable(desc_fn):
        describe = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await describe(
            domain=ctx.domain.name, fetcher_id=fetcher_id, entity=ctx.entity
        )
        return DescribeResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    raise HTTPException(
        501,
        "Domain does not implement describe_value and ValuesService has no describe",
    )
