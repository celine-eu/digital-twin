from __future__ import annotations

import logging
import math
from datetime import timedelta

from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext
from celine.dt.modules.ev_charging.mappers import (
    EVChargingReadinessInputMapper,
    EVChargingReadinessOutputMapper,
)
from celine.dt.modules.ev_charging.models import (
    EVChargingReadinessConfig,
    EVChargingReadinessResult,
)

logger = logging.getLogger(__name__)


class EVChargingReadinessApp(DTApp[EVChargingReadinessConfig, EVChargingReadinessResult]):
    """Decision-ready indicator for EV charging based on PV forecasts + uncertainty."""

    key = "ev-charging-readiness"
    version = "1.0.0"

    config_type = EVChargingReadinessConfig
    result_type = EVChargingReadinessResult

    input_mapper = EVChargingReadinessInputMapper()
    output_mapper = EVChargingReadinessOutputMapper()

    async def run(
        self,
        config: EVChargingReadinessConfig,
        context: RunContext,
    ) -> EVChargingReadinessResult:
        start = config.start_utc or context.now
        end = start + timedelta(hours=config.window_hours)

        # Use a small bounding box to avoid exact-float equality on lat/lon
        lat_eps = 0.02
        lon_eps = 0.02
        lat_min = config.location.lat - lat_eps
        lat_max = config.location.lat + lat_eps
        lon_min = config.location.lon - lon_eps
        lon_max = config.location.lon + lon_eps

        # --- 1) DWD solar energy (kWh/m^2 cumulative within window) ----------------
        try:
            dwd_result = await context.values.fetch(
                fetcher_id="ev-charging.dwd_solar_energy",
                payload={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                },
                limit=5000,
                offset=0,
                request_scope=context.request_scope,
            )
        except Exception:
            logger.exception("Failed fetching DWD solar energy values")
            raise

        dwd_rows = dwd_result.items

        solar_total = 0.0
        if dwd_rows:
            solar_total = float(max(r.get("solar_energy_kwh_per_m2", 0.0) for r in dwd_rows))

        # --- 2) Hourly weather (cloudiness uncertainty) ---------------------------
        weather_fetcher_id = (
            "ev-charging.weather_hourly_by_location"
            if config.weather_location_id
            else "ev-charging.weather_hourly_by_bbox"
        )
        weather_payload: dict[str, object] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

        if config.weather_location_id:
            weather_payload["location_id"] = config.weather_location_id
        else:
            weather_payload.update(
                {
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                }
            )

        try:
            weather_result = await context.values.fetch(
                fetcher_id=weather_fetcher_id,
                payload=weather_payload,
                limit=10000,
                offset=0,
                request_scope=context.request_scope,
            )
        except Exception:
            logger.exception("Failed fetching hourly weather values")
            raise

        weather_rows = weather_result.items

        clouds = [float(r.get("clouds", 0.0)) for r in weather_rows if r.get("clouds") is not None]
        if clouds:
            mean_clouds = sum(clouds) / len(clouds)
            variance = sum((c - mean_clouds) ** 2 for c in clouds) / len(clouds)
            std_clouds = math.sqrt(variance)
        else:
            mean_clouds, std_clouds = 100.0, 50.0

        # --- 3) Decision indicators ------------------------------------------------
        window_hours = float(config.window_hours)

        expected_pv_kwh = solar_total * config.pv_capacity_kw
        ev_capacity_kwh = config.ev_charging_capacity_kw * window_hours

        pv_to_ev_ratio = expected_pv_kwh / ev_capacity_kwh if ev_capacity_kwh > 0 else 0.0

        # Confidence: decreases with cloud variability (std), normalized to [0,1]
        # Heuristic normalization: std=0 -> 1.0, std=50 -> 0.5, std=100 -> 0.0
        confidence = max(0.0, min(1.0, 1.0 - (std_clouds / 100.0)))

        if std_clouds > 60.0:
            indicator = "UNSTABLE"
        elif pv_to_ev_ratio >= config.optimal_ratio:
            indicator = "OPTIMAL"
        elif pv_to_ev_ratio >= config.marginal_ratio:
            indicator = "MARGINAL"
        else:
            indicator = "SUBOPTIMAL"

        drivers: list[str] = []
        recommendations: list[str] = []

        if pv_to_ev_ratio < config.marginal_ratio:
            drivers.append("low PV surplus vs charging capacity")
            recommendations.append("Encourage delayed charging after 18:00")
        if std_clouds > 40.0:
            drivers.append("high cloud variability expected")
            recommendations.append("Prioritize essential fleet vehicles")

        return EVChargingReadinessResult(
            community_id=config.community_id,
            start_utc=start,
            end_utc=end,
            expected_pv_kwh=expected_pv_kwh,
            ev_charging_capacity_kwh=ev_capacity_kwh,
            charging_indicator=indicator,
            confidence=round(confidence, 2),
            drivers=drivers,
            recommendations=recommendations,
        )
