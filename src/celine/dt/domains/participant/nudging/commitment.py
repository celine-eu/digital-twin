"""Flexibility commitment handling: schedule and send reminders via nudging."""

import asyncio
import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from celine.dt.contracts.subscription import EventContext
from celine.sdk.nudging.client import NudgingAdminClient
from celine.sdk.openapi.nudging.models import DigitalTwinEvent

logger = logging.getLogger(__name__)


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


async def _send_reminder(ctx: EventContext, payload: FlexibilityCommittedPayload) -> None:
    """Send the 'It's time!' nudge via the nudging admin client."""
    window_start = (
        payload.window_start
        if isinstance(payload.window_start, datetime)
        else datetime.fromisoformat(str(payload.window_start))
    )
    window_end = (
        payload.window_end
        if isinstance(payload.window_end, datetime)
        else datetime.fromisoformat(str(payload.window_end))
    )

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


async def _reminder_task(ctx: EventContext, payload: FlexibilityCommittedPayload) -> None:
    """Sleep until window_start, then fire the reminder nudge.

    This is the scheduling abstraction: today it uses asyncio.sleep.
    Replace this function body with APScheduler / Celery / etc. when needed.
    """
    window_start = (
        payload.window_start
        if isinstance(payload.window_start, datetime)
        else datetime.fromisoformat(str(payload.window_start))
    )
    delay = (_as_utc(window_start) - datetime.now(timezone.utc)).total_seconds()
    if delay > 0:
        logger.debug(
            "Scheduling flexibility_reminder for commitment=%s in %.0fs",
            payload.commitment_id,
            delay,
        )
        await asyncio.sleep(delay)

    await _send_reminder(ctx, payload)


def schedule_flexibility_reminder(
    ctx: EventContext, payload: FlexibilityCommittedPayload
) -> None:
    """Schedule a reminder nudge to fire at window_start.

    Non-blocking: spawns an asyncio task and returns immediately.
    The task is best-effort — lost on process restart (acceptable for demo;
    swap _reminder_task body for a durable scheduler when needed).
    """
    asyncio.create_task(
        _reminder_task(ctx, payload),
        name=f"flexibility_reminder_{payload.commitment_id}",
    )
    logger.debug(
        "Scheduled reminder task for commitment=%s user=%s window_start=%s",
        payload.commitment_id,
        payload.user_id,
        payload.window_start,
    )
