import logging
from datetime import datetime

from pydantic import BaseModel

from celine.dt.contracts.subscription import EventContext
from celine.dt.core.clients.dataset_api import DatasetSqlApiClient
from celine.sdk.nudging.client import NudgingAdminClient
from celine.sdk.openapi.nudging.models import DigitalTwinEvent

logger = logging.getLogger(__name__)

# Points per kWh of virtual self-consumption — mirrors webapp suggestions.py
POINTS_PER_KWH = 10

# Gold table produced by rec_it pipeline
_TABLE = "ds_dev_gold.rec_virtual_consumption_per_device_15m"


class FlexibilityCommittedPayload(BaseModel):
    user_id: str
    community_id: str = ""
    commitment_id: str
    device_id: str
    window_start: datetime
    window_end: datetime
    reward_points_estimated: int = 0


async def notify_commitment_settled(
    ctx: EventContext, payload: FlexibilityCommittedPayload
) -> None:
    """Compute actual settlement from rec_it gold data and send nudging event.

    Queries rec_virtual_consumption_per_device_15m for the committed window,
    sums virtual_consumption_kwh for the device, derives actual reward points,
    then sends a commitment_settled event to the nudging tool.
    """
    dataset: DatasetSqlApiClient = ctx.infra.clients_registry.get("dataset_api")

    actual_kwh = 0.0
    try:
        rows = await dataset.query(
            sql=(
                f"SELECT SUM(virtual_consumption_kwh) AS total "
                f"FROM {_TABLE} "
                f"WHERE device_id = '{payload.device_id}' "
                f"  AND ts >= '{payload.window_start.isoformat()}' "
                f"  AND ts < '{payload.window_end.isoformat()}'"
            ),
            limit=1,
        )
        if rows and rows[0].get("total") is not None:
            actual_kwh = float(rows[0]["total"])
    except Exception as exc:
        logger.warning(
            "Failed to query virtual consumption for commitment=%s device=%s: %s",
            payload.commitment_id,
            payload.device_id,
            exc,
        )
        # Settlement data not yet available; skip nudge rather than using estimated
        return

    reward_points_actual = round(actual_kwh * POINTS_PER_KWH)
    period = payload.window_start.strftime("%Y-%m-%d")

    nudging_admin_client: NudgingAdminClient = ctx.infra.clients_registry.get(
        "nudging_admin_client"
    )

    nudge_payload = {
        "event_type": "commitment_settled",
        "user_id": payload.user_id,
        "community_id": payload.community_id,
        "facts": {
            "facts_version": "1.0",
            "scenario": "commitment_settled",
            "commitment_id": payload.commitment_id,
            "actual_kwh": str(round(actual_kwh, 3)),
            "reward_points_actual": str(reward_points_actual),
            "period": period,
        },
    }

    try:
        await nudging_admin_client.ingest_event(DigitalTwinEvent.from_dict(nudge_payload))
        logger.debug(
            "Sent commitment_settled nudge to user=%s commitment=%s actual_kwh=%.3f points=%d",
            payload.user_id,
            payload.commitment_id,
            actual_kwh,
            reward_points_actual,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send commitment_settled nudge to user=%s: %s",
            payload.user_id,
            exc,
        )
