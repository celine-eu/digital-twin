# celine/dt/domains/participant/routes/flexibility.py
"""Flexibility assessment and demand response."""
from typing import Any

from fastapi import APIRouter, Depends

from celine.dt.api.context import get_ctx_auth, Ctx
from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)

__prefix__ = ""
__tags__ = ["participant-flexibility"]

router = APIRouter()


@router.get("/flexibility")
async def get_flexibility(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> dict[str, Any]:
    """Flexibility assessment for demand response.

    Combines registry data with local calculations.
    """
    # TODO: Implement actual flexibility calculation
    # Could use entity.metadata.community_key to query time-series data
    return {
        "participant_id": ctx.entity.id,
        "community_key": ctx.entity.metadata.get("community_key"),
        "flexible_load_kw": None,
        "available_window_hours": None,
        "note": "Implement with actual flexibility analysis",
    }
