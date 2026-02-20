import logging

from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext
from celine.dt.core.broker.decorators import on_event
from celine.sdk.broker import PipelineRunEvent

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
        logger.debug(f"{payload.namespace}.{payload.flow}")
