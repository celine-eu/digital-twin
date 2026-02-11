from __future__ import annotations
from typing import Any, Awaitable, Callable, cast

from fastapi import APIRouter, Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.routes import (
    DescribeResponseSchema,
    SimulationDescriptorSchema,
)

router = APIRouter(prefix="/simulations")


@router.get(
    "",
    response_model=list[SimulationDescriptorSchema],
    operation_id="list_simulations",
)
async def list_simulations(
    ctx: Ctx = Depends(get_ctx_auth),
) -> list[SimulationDescriptorSchema]:
    fn = getattr(ctx.domain, "list_simulations", None)
    if callable(fn):
        list_simulations = cast(Callable[..., Awaitable[list[Any]]], fn)
        items = await list_simulations(ctx=ctx)
        return [
            (
                SimulationDescriptorSchema.model_validate(i)
                if not isinstance(i, SimulationDescriptorSchema)
                else i
            )
            for i in items
        ]

    raise HTTPException(
        501,
        "Domain does not implement list_simulations",
    )


@router.get(
    "/{sim_key}/describe",
    response_model=DescribeResponseSchema,
    operation_id="describe_simulation",
)
async def describe_simulation(
    sim_key: str, ctx: Ctx = Depends(get_ctx_auth)
) -> DescribeResponseSchema:
    fn = getattr(ctx.domain, "describe_simulation", None)
    if callable(fn):
        describe_simulation = cast(Callable[..., Awaitable[Any]], fn)
        payload = await describe_simulation(ctx=ctx, sim_key=sim_key)
        return DescribeResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    desc_fn = getattr(ctx.values_service, "describe_simulation", None)
    if callable(desc_fn):
        describe_simulation = cast(Callable[..., Awaitable[Any]], fn)
        payload = await describe_simulation(
            domain=ctx.domain.name, entity=ctx.entity, sim_key=sim_key
        )
        return DescribeResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )

    raise HTTPException(
        501,
        "Domain does not implement describe_simulation and ValuesService has no describe_simulation",
    )
