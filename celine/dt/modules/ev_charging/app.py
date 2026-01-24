# celine/dt/modules/ev_charging/app.py
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


class EVChargingReadinessApp(
    DTApp[EVChargingReadinessConfig, EVChargingReadinessResult]
):
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

        # Bounding box to avoid exact float matching
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
            # cumulative series -> max as total up to window end
            solar_total = float(
                max(r.get("solar_energy_kwh_per_m2", 0.0) for r in dwd_rows)
            )

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

        clouds = [
            float(r.get("clouds", 0.0))
            for r in weather_rows
            if r.get("clouds") is not None
        ]
        if clouds:
            mean_clouds = sum(clouds) / len(clouds)
            variance = sum((c - mean_clouds) ** 2 for c in clouds) / len(clouds)
            std_clouds = math.sqrt(variance)
        else:
            # no data -> pessimistic uncertainty
            mean_clouds, std_clouds = 100.0, 50.0

        # --- 3) Confidence + PV projection ---------------------------------------
        # std=0  -> 1.0
        # std>=50 -> 0.0
        confidence = max(0.0, min(1.0, 1.0 - (std_clouds / 50.0)))

        # Explainable proxy:
        # expected_pv_kwh ≈ pv_capacity_kw × solar_total_kwh_per_m2 × (1 - mean_clouds_pct)
        clouds_factor = max(0.0, min(1.0, 1.0 - (mean_clouds / 100.0)))
        expected_pv_kwh = float(config.pv_capacity_kw * solar_total * clouds_factor)

        ev_capacity_kwh = float(config.ev_charging_capacity_kw * config.window_hours)

        pv_ev_ratio = (
            (expected_pv_kwh / ev_capacity_kwh) if ev_capacity_kwh > 0 else 0.0
        )

        # --- 4) Indicator classification -----------------------------------------
        drivers: list[str] = []
        recs: list[str] = []

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

        return EVChargingReadinessResult(
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
