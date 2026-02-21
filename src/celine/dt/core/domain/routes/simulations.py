from __future__ import annotations
from typing import Any, Awaitable, Callable, cast

from fastapi import APIRouter, Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.routes import (
    SimulationDescriptorSchema,
)
from celine.dt.core.domain.base import DTDomain

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

