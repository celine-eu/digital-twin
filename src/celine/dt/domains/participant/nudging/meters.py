from dataclasses import dataclass
import logging

from celine.dt.contracts.subscription import EventContext
from celine.sdk.rec_registry.client import RecRegistryAdminClient
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

async def notify_meters_anomalies(ctx: EventContext):

    anomalies = await ctx.infra.values_service.fetch(
        fetcher_id="it-participant.meter_anomalies",
        payload={},
    )

    if not anomalies or anomalies.count == 0:
        logger.debug("No meter trasmission anomalies found")

    sensor_ids: list[str] = []
    for r in anomalies.items:
        sensor_id = r.get("device_id")
        if sensor_id:
            sensor_ids.append(sensor_id)

    logger.debug(f"Meter with transmission gaps: {sensor_ids}")

    rec_registry_admin: RecRegistryAdminClient = ctx.infra.clients_registry.get("rec_registry_admin")
    assets = await rec_registry_admin.lookup_asset_by_sensor_ids(sensor_ids=sensor_ids)

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=3)

    period = now.strftime("%Y-%m")
    window_start = now.strftime("%H:%M")
    window_end = end.strftime("%H:%M")


    for asset in assets:
        logger.debug(f"Notifying anomalies for asset type={asset.asset_type} user_id={asset.owner_user_id} community={asset.community_key}")
        
        # TODO check 
        payload = {
            "event_type": "nudging_meter_anomlay",
            "user_id": asset.owner_user_id,
            "community_id": asset.community_key,
            "facts": {
                "facts_version": "1.0",
                "scenario": "meter_anomaly",
                "event": f"Device '{asset.name}' is not sending data",
                "period": period,
                "window_start": window_start,
                "window_end": window_end,

            }
        }

        await ctx.infra.broker.publish_event(
            topic=f"celine/nudging/notify/{asset.owner_user_id}",
            payload=payload,
        )


