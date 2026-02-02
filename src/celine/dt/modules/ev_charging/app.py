# celine/dt/modules/ev_charging/app_with_events.py
"""
EV Charging Readiness app with event publishing.

This shows how to integrate event publishing into an existing DT app.
The app emits events when it computes a new readiness indicator.
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext
from celine.dt.modules.ev_charging.events import create_ev_charging_readiness_event
from celine.dt.modules.ev_charging.mappers import (
    EVChargingReadinessInputMapper,
    EVChargingReadinessOutputMapper,
)
from celine.dt.modules.ev_charging.models import (
    EVChargingReadinessConfig,
    EVChargingReadinessResult,
)

logger = logging.getLogger(__name__)


class EVChargingReadinessApp(
    DTApp[EVChargingReadinessConfig, EVChargingReadinessResult]
):
    """
    Decision-ready indicator for EV charging based on PV forecasts + uncertainty.

    This version publishes events to the configured broker after computing
    the readiness indicator.
    """

    key = "ev-charging-readiness"
    version = "1.1.0"  # Bumped version for event support

    config_type = EVChargingReadinessConfig
    result_type = EVChargingReadinessResult

    input_mapper = EVChargingReadinessInputMapper()
    output_mapper = EVChargingReadinessOutputMapper()

    async def run(
        self,
        config: EVChargingReadinessConfig,
        context: RunContext,
    ) -> EVChargingReadinessResult:
        """
        Execute the EV charging readiness computation and publish result event.
        """
        start = config.start_utc or context.now
        end = start + timedelta(hours=config.window_hours)

        # Bounding box to avoid exact float matching
        lat_eps = 0.02
        lon_eps = 0.02
        lat_min = config.location.lat - lat_eps
        lat_max = config.location.lat + lat_eps
        lon_min = config.location.lon - lon_eps
        lon_max = config.location.lon + lon_eps

        # --- 1) DWD solar energy (kWh/m^2 cumulative within window) ----------------
        solar_result = await context.values.fetch(
            fetcher_id="ev-charging.dwd_solar_energy",
            payload={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            },
        )

        solar_total = sum(
            row.get("solar_energy_kwh_per_m2", 0) for row in solar_result.items
        )

        # --- 2) Weather / cloudiness (for uncertainty) ----------------------------
        if config.weather_location_id:
            weather_result = await context.values.fetch(
                fetcher_id="ev-charging.weather_hourly_by_location",
                payload={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "location_id": config.weather_location_id,
                },
            )
        else:
            weather_result = await context.values.fetch(
                fetcher_id="ev-charging.weather_hourly_by_bbox",
                payload={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                },
            )

        clouds = [row.get("clouds", 50) for row in weather_result.items] or [50]
        mean_clouds = sum(clouds) / len(clouds)
        std_clouds = (
            math.sqrt(sum((c - mean_clouds) ** 2 for c in clouds) / len(clouds))
            if len(clouds) > 1
            else 0.0
        )

        # --- 3) PV estimate -------------------------------------------------------
        pv_efficiency = 0.18
        panel_area_m2 = config.pv_capacity_kw / 0.2
        expected_pv_kwh = solar_total * panel_area_m2 * pv_efficiency

        # --- 4) EV charging capacity ----------------------------------------------
        ev_capacity_kwh = config.ev_charging_capacity_kw * config.window_hours

        # --- 5) Indicator logic ---------------------------------------------------
        if ev_capacity_kwh > 0:
            pv_ev_ratio = expected_pv_kwh / ev_capacity_kwh
        else:
            pv_ev_ratio = 0.0

        confidence = max(0, 1 - std_clouds / 50)

        drivers: list[str] = []
        recs: list[str] = []
        indicator: str

        if confidence < config.unstable_confidence:
            indicator = "UNSTABLE"
            drivers.append("forecast uncertainty is high (cloud variability)")
            recs.append(
                "Avoid aggressive charging recommendations; re-evaluate closer to real time."
            )
        else:
            if pv_ev_ratio >= config.optimal_ratio:
                indicator = "OPTIMAL"
                drivers.append(
                    "expected PV energy is sufficient for planned EV charging"
                )
                if mean_clouds > 50:
                    drivers.append(
                        "high cloudiness reduces yield, but surplus remains adequate"
                    )
                recs.append(
                    "Encourage EV charging during this window to maximize self-consumption."
                )
            elif pv_ev_ratio >= config.marginal_ratio:
                indicator = "MARGINAL"
                drivers.append("PV energy may partially cover EV charging demand")
                drivers.append("some grid import is likely without coordination")
                recs.append(
                    "Stagger charging sessions and prioritize essential vehicles."
                )
                recs.append("Shift flexible charging to peak PV hours (midday).")
            else:
                indicator = "SUBOPTIMAL"
                drivers.append(
                    "expected PV energy is low relative to EV charging capacity"
                )
                if mean_clouds >= 60:
                    drivers.append("high cloud cover expected during the window")
                recs.append("Recommend delayed charging or reduced charging power.")
                recs.append(
                    "Prioritize critical charging sessions; consider off-peak tariffs."
                )

        result = EVChargingReadinessResult(
            community_id=config.community_id,
            start_utc=start,
            end_utc=end,
            window_hours=config.window_hours,
            expected_pv_kwh=expected_pv_kwh,
            ev_charging_capacity_kwh=ev_capacity_kwh,
            indicator=indicator,  # type: ignore
            confidence=float(confidence),
            drivers=drivers,
            recommendations=recs,
            mean_clouds_pct=float(mean_clouds),
            clouds_std_pct=float(std_clouds),
            solar_energy_kwh_per_m2_total=float(solar_total),
            pv_ev_ratio=float(pv_ev_ratio),
        )

        # --- 6) Publish event (NEW) -----------------------------------------------
        await self._publish_result_event(result, context)

        return result

    async def _publish_result_event(
        self,
        result: EVChargingReadinessResult,
        context: RunContext,
    ) -> None:
        """
        Publish the computed result as an event to the broker.
        """
        if not context.has_broker():
            logger.debug("No broker configured, skipping event publication")
            return

        # Create the event using the factory function
        event = create_ev_charging_readiness_event(
            community_id=result.community_id,
            window_start=result.start_utc,
            window_end=result.end_utc,
            window_hours=result.window_hours,
            expected_pv_kwh=result.expected_pv_kwh,
            ev_charging_capacity_kwh=result.ev_charging_capacity_kwh,
            pv_ev_ratio=result.pv_ev_ratio,
            indicator=result.indicator,
            confidence=result.confidence,
            drivers=result.drivers,
            recommendations=result.recommendations,
            mean_clouds_pct=result.mean_clouds_pct,
            clouds_std_pct=result.clouds_std_pct,
            solar_energy_kwh_per_m2=result.solar_energy_kwh_per_m2_total,
            app_version=self.version,
            correlation_id=context.request_id,
        )

        # Construct topic: dt/ev-charging/readiness-computed/{community_id}
        topic = f"dt/ev-charging/readiness-computed/{result.community_id}"

        # Publish the event
        pub_result = await context.publish_event(event, topic=topic)

        if pub_result.success:
            logger.info(
                "Published EV charging readiness event for %s (msg_id=%s)",
                result.community_id,
                pub_result.message_id,
            )
        else:
            logger.warning(
                "Failed to publish event for %s: %s",
                result.community_id,
                pub_result.error,
            )
