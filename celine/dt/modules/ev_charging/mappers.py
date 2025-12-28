from __future__ import annotations

from typing import Mapping

from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.modules.ev_charging.models import (
    EVChargingReadinessConfig,
    EVChargingReadinessResult,
)


class EVChargingReadinessInputMapper(InputMapper[EVChargingReadinessConfig]):
    input_type = EVChargingReadinessConfig

    def map(self, raw: Mapping) -> EVChargingReadinessConfig:
        return EVChargingReadinessConfig.model_validate(raw)


class EVChargingReadinessOutputMapper(OutputMapper[EVChargingReadinessResult]):
    output_type = EVChargingReadinessResult

    def map(self, result: EVChargingReadinessResult) -> dict:
        # CamelCase + @type for demo friendliness
        return {
            "@type": "EVChargingReadiness",
            "communityId": result.community_id,
            "startUTC": result.start_utc.isoformat(),
            "endUTC": result.end_utc.isoformat(),
            "windowHours": result.window_hours,
            "expectedPVKWh": result.expected_pv_kwh,
            "evChargingCapacityKWh": result.ev_charging_capacity_kwh,
            "chargingIndicator": result.indicator,
            "confidence": result.confidence,
            "drivers": result.drivers,
            "recommendations": result.recommendations,
            # Details (handy for debugging + dashboards)
            "meanCloudsPct": result.mean_clouds_pct,
            "cloudsStdPct": result.clouds_std_pct,
            "solarEnergyKWhPerM2Total": result.solar_energy_kwh_per_m2_total,
            "pvEvRatio": result.pv_ev_ratio,
        }
