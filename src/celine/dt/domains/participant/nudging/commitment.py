"""Flexibility commitment handling: register and send reminders via nudging.

Reminders are stored in-memory when a commitment arrives and fired on the
next pipeline tick (meters-flow, every 5 min) once window_start has passed.

The scheduling abstraction is preserved: replace _pending with a durable
store (Redis, DB) and point check_pending_reminders() at an APScheduler job
when process-restart durability is needed.
"""
import logging
from datetime import datetime, timezone
from typing import Dict

from pydantic import BaseModel

from celine.dt.contracts.subscription import EventContext
from celine.sdk.nudging.client import NudgingAdminClient
from celine.sdk.openapi.nudging.models import DigitalTwinEvent

logger = logging.getLogger(__name__)

# In-memory store: commitment_id → payload.  Best-effort; lost on restart.
_pending: Dict[str, "FlexibilityCommittedPayload"] = {}


class FlexibilityCommittedPayload(BaseModel):
    user_id: str
    community_id: str = ""
    commitment_id: str
    device_id: str
    window_start: datetime
    window_end: datetime
    reward_points_estimated: int = 0


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


async def _send_reminder(ctx: EventContext, payload: "FlexibilityCommittedPayload") -> None:
    """Send the 'It's time!' nudge via the nudging admin client."""
    window_start = _as_utc(_coerce_dt(payload.window_start))
    window_end = _as_utc(_coerce_dt(payload.window_end))

    nudging_admin_client: NudgingAdminClient = ctx.infra.clients_registry.get(
        "nudging_admin_client"
    )
    nudge_payload = {
        "event_type": "flexibility_reminder",
        "user_id": payload.user_id,
        "community_id": payload.community_id,
        "facts": {
            "facts_version": "1.0",
            "scenario": "flexibility_reminder",
            "commitment_id": payload.commitment_id,
            "window_start": window_start.strftime("%H:%M"),
            "window_end": window_end.strftime("%H:%M"),
            "reward_points_estimated": str(payload.reward_points_estimated),
            "period": window_start.strftime("%Y-%m-%d"),
        },
    }
    try:
        await nudging_admin_client.ingest_event(DigitalTwinEvent.from_dict(nudge_payload))
        logger.info(
            "Sent flexibility_reminder user=%s commitment=%s window=%s-%s pts=%d",
            payload.user_id,
            payload.commitment_id,
            window_start.strftime("%H:%M"),
            window_end.strftime("%H:%M"),
            payload.reward_points_estimated,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send flexibility_reminder for commitment=%s: %s",
            payload.commitment_id,
            exc,
        )


def schedule_flexibility_reminder(
    ctx: EventContext, payload: "FlexibilityCommittedPayload"
) -> None:
    """Register a commitment so its reminder fires on the next pipeline tick.

    Non-blocking.  The backing store is in-memory (best-effort; lost on
    restart).  Swap _pending for a durable store when needed.
    """
    _pending[payload.commitment_id] = payload
    logger.debug(
        "Registered flexibility reminder commitment=%s user=%s window_start=%s",
        payload.commitment_id,
        payload.user_id,
        payload.window_start,
    )


async def check_pending_reminders(ctx: EventContext) -> None:
    """Fire reminders whose window has opened; silently drop expired ones.

    Called on every pipeline tick (meters-flow runs every 5 min).
    """
    now = datetime.now(timezone.utc)
    to_fire = []
    to_discard = []

    for payload in list(_pending.values()):
        ws = _as_utc(_coerce_dt(payload.window_start))
        we = _as_utc(_coerce_dt(payload.window_end))
        if ws <= now:
            (to_fire if now < we else to_discard).append(payload)

    for payload in to_fire + to_discard:
        _pending.pop(payload.commitment_id, None)

    if to_discard:
        logger.info(
            "Discarded %d expired flexibility reminders (window already closed)",
            len(to_discard),
        )

    for payload in to_fire:
        await _send_reminder(ctx, payload)
