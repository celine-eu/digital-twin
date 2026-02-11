from __future__ import annotations
from typing import Any, Awaitable, Callable, cast

from fastapi import APIRouter, Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.routes import SummaryResponseSchema

router = APIRouter(prefix="/summary")


@router.get(
    "",
    response_model=SummaryResponseSchema,
    operation_id="get_summary",
)
async def get_summary(ctx: Ctx = Depends(get_ctx_auth)) -> SummaryResponseSchema:
    fn = getattr(ctx.domain, "get_summary", None)
    if callable(fn):
        get_summary = cast(Callable[..., Awaitable[Any | list[Any]]], fn)
        payload = await get_summary(ctx=ctx)
        return SummaryResponseSchema(
            payload=payload if isinstance(payload, dict) else {"value": payload}
        )
    raise HTTPException(
        501,
        "Domain does not implement get_summary",
    )
