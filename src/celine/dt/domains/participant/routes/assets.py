# celine/dt/domains/participant/routes/assets.py
"""Participant assets and delivery points."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Depends

from celine.dt.api.context import get_ctx_auth, Ctx

from celine.sdk.openapi.rec_registry.schemas import (
    UserAssetsResponseSchema,
    UserDeliveryPointsResponseSchema,
)
from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)

__prefix__ = ""
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/assets", operation_id="assets")
async def get_assets(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> UserAssetsResponseSchema:
    """Get participant's assets from registry."""
    token = ctx.token
    try:
        assets = await ctx.domain.rec_registry.get_my_assets(token=token)
        if assets is None:
            raise HTTPException(404, "Assets not found or access denied")
        return assets
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch assets: %s", e)
        raise HTTPException(500, "Failed to fetch asset details")


@router.get("/delivery-points", operation_id="delivery_points")
async def get_delivery_points(
    ctx: Ctx = Depends(get_ctx_auth),
) -> UserDeliveryPointsResponseSchema:
    """Get participant's delivery points from registry."""
    token = ctx.token
    try:
        dps = await ctx.domain.rec_registry.get_my_delivery_points(token=token)
        if dps is None:
            raise HTTPException(404, "Delivery points not found or access denied")
        return dps
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch delivery points: %s", e)
        raise HTTPException(500, "Failed to fetch delivery point details")
