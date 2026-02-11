# celine/dt/domains/energy_community/routes/summary.py
"""Community summary."""
from typing import Any

from fastapi import APIRouter, Depends

from celine.dt.api.context import get_ctx, Ctx
from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)

__prefix__ = ""
__tags__ = ["community-info"]

router = APIRouter()


@router.get("/summary")
async def get_summary(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> dict[str, Any]:
    """High-level community summary."""
    return {
        "community_id": ctx.entity.id,
        "domain": ctx.domain.name,
        "domain_type": ctx.domain.domain_type,
        "version": ctx.domain.version,
        "metadata": ctx.entity.metadata,
    }
