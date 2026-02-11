from __future__ import annotations

from typing import cast
from fastapi import Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.entity import EntityInfo
from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain

ITCommunityCtx = Ctx[ITEnergyCommunityDomain, EntityInfo]


async def get_it_community_ctx(
    ctx: Ctx = Depends(get_ctx_auth),
) -> ITCommunityCtx:
    if not isinstance(ctx.domain, ITEnergyCommunityDomain):
        # This should never happen if mounted correctly, but it's a good invariant.
        raise HTTPException(500, "Invalid domain for IT community context")
    return cast(ITCommunityCtx, ctx)
