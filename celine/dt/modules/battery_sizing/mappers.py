from __future__ import annotations
from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.modules.battery_sizing.models import BatterySizingInputs
from celine.dt.core.timeseries import TimeSeries
from celine.dt.modules.battery_sizing.models import BatterySizingResult


class BatterySizingInputMapper(InputMapper[BatterySizingInputs]):

    def map(self, raw: dict) -> BatterySizingInputs:
        return BatterySizingInputs(
            demand=TimeSeries(**raw["demand"]),
            pv=TimeSeries(**raw["pv"]),
            roundtrip_efficiency=raw.get("roundtrip_efficiency", 0.92),
            max_capacity_kwh=raw.get("max_capacity_kwh", 200),
            capacity_step_kwh=raw.get("capacity_step_kwh", 5),
        )


class BatterySizingOutputMapper(OutputMapper[BatterySizingResult]):
    def map(self, obj: BatterySizingResult) -> dict:
        return {
            "@type": "BatterySizingResult",
            "capacityKWh": obj.capacity_kwh,
            "gridImportKWh": obj.grid_import_kwh,
            "selfConsumptionRatio": obj.self_consumption_ratio,
        }
