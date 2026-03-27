import logging
from datetime import datetime, timezone, timedelta

from celine.dt.contracts.subscription import EventContext
from celine.sdk.openapi.nudging.models import DigitalTwinEvent
from celine.sdk.nudging.client import NudgingAdminClient
from celine.sdk.rec_registry.client import RecRegistryAdminClient

logger = logging.getLogger(__name__)


async def notify_meters_anomalies(ctx: EventContext):
    anomalies = await ctx.infra.values_service.fetch(
        fetcher_id="it-participant.meter_anomalies",
        payload={},
    )

    if not anomalies or anomalies.count == 0:
        logger.debug("No meter trasmission anomalies found")
        return

    sensor_ids: list[str] = []
    for r in anomalies.items:
        sensor_id = r.get("device_id")
        if sensor_id:
            sensor_ids.append(sensor_id)

    sensor_ids = list(dict.fromkeys(sensor_ids))
    if not sensor_ids:
        logger.debug("No sensor ids found in meter anomalies payload")
        return

    logger.debug(f"Meter with transmission gaps: {sensor_ids}")

    rec_registry_admin: RecRegistryAdminClient = ctx.infra.clients_registry.get(
        "rec_registry_admin"
    )
    assets = await rec_registry_admin.lookup_asset_by_sensor_ids(sensor_ids=sensor_ids)
    if not assets:
        logger.debug("No assets found for sensor ids with transmission gaps")
        return

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=3)

    time = now.strftime("%Y-%m-%d")
    window_start = now.strftime("%H:%M")
    window_end = end.strftime("%H:%M")
    nudging_admin_client: NudgingAdminClient = ctx.infra.clients_registry.get(
        "nudging_admin_client"
    )

    for asset in assets:
        logger.debug(
            f"Notifying anomalies for asset type={asset.asset_type} user_id={asset.owner_user_id} community={asset.community_key}"
        )

        device_name = getattr(asset, "name", None) or "smart meter"
        payload = {
            "event_type": "meter_anomaly",
            "user_id": asset.owner_user_id,
            "community_id": asset.community_key,
            "facts": {
                "facts_version": "1.0",
                "scenario": "meter_anomaly",
                "time": time,
                "device_name": device_name,
                "window_start": window_start,
                "window_end": window_end,
            },
        }
        await nudging_admin_client.ingest_event(DigitalTwinEvent.from_dict(payload))
