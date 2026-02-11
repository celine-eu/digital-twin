# celine/dt/domains/participant/routes/profile.py
"""Participant profile routes - registry integration."""
import logging

from fastapi import APIRouter, HTTPException, Depends

from celine.sdk.openapi.rec_registry.schemas import (
    UserMeResponseSchema,
    UserCommunityDetailSchema,
    UserMemberDetailSchema,
)
from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)

__prefix__ = ""
__tags__ = ["participant-profile"]

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profile")
async def get_profile(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> UserMeResponseSchema:
    """Get participant profile from registry."""
    participant = await ctx.domain.get_participant(ctx.request)
    if participant is None:
        raise HTTPException(404, "Participant not found or access denied")
    return participant


@router.get("/community")
async def get_community(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> UserCommunityDetailSchema:
    """Get participant's community details from registry."""
    token = ctx.token
    try:
        community = await ctx.domain.rec_registry.get_my_community(token=token)
        if community is None:
            raise HTTPException(404, "Community not found or access denied")
        return community
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch community: %s", e)
        raise HTTPException(500, "Failed to fetch community details")


@router.get("/member")
async def get_member(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
) -> UserMemberDetailSchema:
    """Get participant's member details from registry."""
    token = ctx.token
    try:
        member = await ctx.domain.rec_registry.get_my_member(token=token)
        if member is None:
            raise HTTPException(404, "Membership not found or access denied")
        return member
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch member: %s", e)
        raise HTTPException(500, "Failed to fetch member details")
