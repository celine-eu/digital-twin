from __future__ import annotations

from typing import cast
from fastapi import Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.entity import EntityInfo
from celine.dt.domains.participant.domain import ITParticipantDomain, ParticipantDomain

ParticipantCtx = Ctx[ITParticipantDomain, EntityInfo]


async def get_participant_ctx(
    ctx: Ctx = Depends(get_ctx_auth),
) -> ParticipantCtx:
    if not isinstance(ctx.domain, ParticipantDomain):
        # This should never happen if mounted correctly, but it's a good invariant.
        raise HTTPException(500, "Invalid domain for participant context")
    return cast(ParticipantCtx, ctx)
