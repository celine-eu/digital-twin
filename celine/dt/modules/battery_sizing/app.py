
from __future__ import annotations
from celine.dt.modules.battery_sizing.models import (
    BatterySizingInputs,
    BatterySizingResult,
)

class BatterySizingApp:
    key = "battery-sizing"
    version = "2.0.0"

    async def run(
        self,
        inputs: BatterySizingInputs,
        context,
    ) -> BatterySizingResult:
        total_demand = inputs.demand.total()
        total_pv = inputs.pv.total()

        capacity = min(inputs.max_capacity_kwh, total_pv)
        grid_import = max(0.0, total_demand - total_pv)

        sc = min(1.0, total_pv / total_demand) if total_demand else 0.0

        return BatterySizingResult(
            capacity_kwh=capacity,
            grid_import_kwh=grid_import,
            self_consumption_ratio=sc,
        )
