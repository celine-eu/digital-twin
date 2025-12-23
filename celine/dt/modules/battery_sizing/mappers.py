from __future__ import annotations
from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.modules.battery_sizing.models import BatterySizingConfig
from celine.dt.core.timeseries import TimeSeries
from celine.dt.modules.battery_sizing.models import BatterySizingResult
from typing import Mapping


class BatterySizingInputMapper(InputMapper):
    input_type = BatterySizingConfig

    def map(self, raw: Mapping) -> BatterySizingConfig:
        try:
            return BatterySizingConfig(
                demand=TimeSeries(**raw["demand"]),
                pv=TimeSeries(**raw["pv"]),
                roundtrip_efficiency=raw.get("roundtrip_efficiency", 0.92),
                max_capacity_kwh=raw.get("max_capacity_kwh", 200),
                capacity_step_kwh=raw.get("capacity_step_kwh", 5),
            )
        except KeyError as exc:
            raise ValueError(
                "Invalid payload: expected 'demand' and 'pv' TimeSeries objects"
            ) from exc


class BatterySizingOutputMapper(OutputMapper):
    output_type = BatterySizingResult

    def map(self, result: BatterySizingResult) -> dict:
        return {
            "@type": "BatterySizingResult",
            "capacityKWh": result.capacity_kwh,
            "gridImportKWh": result.grid_import_kwh,
            "selfConsumptionRatio": result.self_consumption_ratio,
        }
