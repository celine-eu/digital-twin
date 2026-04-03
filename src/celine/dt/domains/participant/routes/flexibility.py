# celine/dt/domains/participant/routes/flexibility.py
"""Flexibility commitment events — MQTT publish proxy."""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)

__prefix__ = ""
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()

FLEXIBILITY_TOPIC_PREFIX = "celine/flexibility/committed"


class FlexibilityCommittedRequest(BaseModel):
    commitment_id: str
    community_id: str
    device_id: str
    window_start: datetime
    window_end: datetime
    reward_points_estimated: int


@router.post(
    "/flexibility/committed",
    operation_id="flexibility_committed",
    status_code=202,
)
async def post_flexibility_committed(
    body: FlexibilityCommittedRequest,
    ctx: ParticipantCtx = Depends(get_participant_ctx),
):
    """Publish a flexibility commitment event to MQTT.

    The BFF calls this when a user accepts a load-shift suggestion.
    The DT publishes the event to MQTT; the @on_event handler catches it
    asynchronously and computes settlement from rec_virtual_consumption_per_device.
    """
    assert ctx.user is not None  # guaranteed by get_ctx_auth via get_participant_ctx
    topic = f"{FLEXIBILITY_TOPIC_PREFIX}/{ctx.entity.id}"
    payload = {
        "user_id": ctx.user.sub,
        "community_id": body.community_id,
        "commitment_id": body.commitment_id,
        "device_id": body.device_id,
        "window_start": body.window_start.isoformat(),
        "window_end": body.window_end.isoformat(),
        "reward_points_estimated": body.reward_points_estimated,
    }

    try:
        await ctx.publish(topic=topic, payload=payload)
        log.debug(
            "Published flexibility.committed for user=%s commitment=%s",
            ctx.user.sub,
            body.commitment_id,
        )
    except Exception as exc:
        log.error(
            "Failed to publish flexibility.committed for user=%s: %s",
            ctx.user.sub,
            exc,
        )
        raise HTTPException(502, "Failed to publish commitment event")

    return {"status": "accepted", "commitment_id": body.commitment_id}
