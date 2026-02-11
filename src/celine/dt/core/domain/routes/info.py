from __future__ import annotations

from fastapi import APIRouter, Depends

from celine.dt.api.context import Ctx, get_ctx_auth

router = APIRouter(prefix="/info")


@router.get("", operation_id="get_info")
async def get_info(ctx: Ctx = Depends(get_ctx_auth)) -> dict:
    # Keep it generic: it should always exist and be cheap
    return {
        "domain": ctx.domain.name,
        "entity": {
            "id": ctx.entity.id,
            "type": ctx.entity.type,
            "metadata": ctx.entity.metadata,
        },
        "request_id": ctx.request_id,
        "timestamp": ctx.timestamp.isoformat(),
        "user": (
            {
                "id": getattr(ctx.user, "sub", None),
                "email": getattr(ctx.user, "email", None),
            }
            if ctx.user
            else None
        ),
    }
