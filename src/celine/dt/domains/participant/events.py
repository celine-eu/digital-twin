import logging

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext
from celine.dt.core.broker.decorators import on_event
from celine.sdk.broker import PipelineRunEvent
from celine.dt.domains.participant.nudging.meters import notify_meters_anomalies
from celine.dt.domains.participant.nudging.flexibility import notify_flexibility_opportunity
from celine.dt.domains.participant.nudging.commitment import (
    FlexibilityCommittedPayload,
    notify_commitment_settled,
)

logger = logging.getLogger(__name__)


@on_event(
    "pipelines.run",
    broker="celine_mqtt",
    topics=["celine/pipelines/runs/+"],
)
async def on_pipeline_run(
    event: DTEvent[PipelineRunEvent], ctx: EventContext
) -> None:

    payload: PipelineRunEvent = event.payload
    logger.debug(f"Got pipeline.runs event {payload.namespace}.{payload.flow} {payload.status}")

    if payload.status != "completed":
        return

    if payload.flow == "meters-flow":
        logger.debug(f"Trigger nudging process for {payload.namespace}.{payload.flow}")
        await notify_meters_anomalies(ctx)
    elif payload.flow == "rec-forecasting-flow":
        logger.debug(f"Trigger flexibility opportunity nudging for {payload.namespace}.{payload.flow}")
        await notify_flexibility_opportunity(ctx)


@on_event(
    "flexibility.committed",
    broker="celine_mqtt",
    topics=["celine/flexibility/committed/+"],
)
async def on_flexibility_committed(
    event: DTEvent[FlexibilityCommittedPayload], ctx: EventContext
) -> None:
    """Settle a flexibility commitment using actual virtual consumption from rec_it gold tables."""
    payload = event.payload
    logger.debug(
        "Processing flexibility.committed for user=%s commitment=%s window=%s/%s",
        payload.user_id,
        payload.commitment_id,
        payload.window_start,
        payload.window_end,
    )
    await notify_commitment_settled(ctx, payload)
