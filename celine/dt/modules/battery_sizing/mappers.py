from __future__ import annotations

from typing import Any, Mapping

from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.modules.battery_sizing.models import BatterySizingInputs, BatterySizingResult


class BatterySizingInputMapper(InputMapper):
    """Accepts either a flat payload or {timeseries: {...}}."""

    def map(self, raw: Any, **context: Any) -> BatterySizingInputs:
        if isinstance(raw, BatterySizingInputs):
            return raw
        if not isinstance(raw, Mapping):
            raise TypeError("BatterySizingInputMapper expects an object/dict payload")

        if "timeseries" in raw and isinstance(raw["timeseries"], Mapping):
            merged = dict(raw)
            ts = dict(raw["timeseries"])
            merged.pop("timeseries", None)
            merged.update(ts)
            return BatterySizingInputs.model_validate(merged)

        return BatterySizingInputs.model_validate(raw)


class BatterySizingOutputMapper(OutputMapper):
    """Minimal JSON-LD-ish output envelope."""

    ontology = "celine"

    def map(self, obj: Any, **context: Any) -> dict[str, Any]:
        if isinstance(obj, BatterySizingResult):
            data = obj.model_dump()
        elif isinstance(obj, Mapping):
            data = dict(obj)
        else:
            raise TypeError("BatterySizingOutputMapper expects a dict-like result")

        return {
            "@id": "urn:celine:dt:app:battery-sizing:result",
            "@type": "BatterySizingResult",
            "capacityKWh": data["capacity_kwh"],
            "powerKW": data["power_kw"],
            "kpis": {
                "totalDemandKWh": data["total_demand_kwh"],
                "totalPvKWh": data["total_pv_kwh"],
                "gridImportKWh": data["grid_import_kwh"],
                "gridExportKWh": data["grid_export_kwh"],
                "selfConsumptionRatio": data["self_consumption_ratio"],
                "selfSufficiencyRatio": data["self_sufficiency_ratio"],
                "batteryThroughputKWh": data["battery_throughput_kwh"],
                "equivalentFullCycles": data["equivalent_full_cycles"],
            },
        }
