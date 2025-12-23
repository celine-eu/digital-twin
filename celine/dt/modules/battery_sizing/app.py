from celine.dt.contracts.app import DTApp
from celine.dt.modules.battery_sizing.models import (
    BatterySizingConfig,
    BatterySizingResult,
)


class BatterySizingApp(DTApp[BatterySizingConfig, BatterySizingResult]):
    key = "battery-sizing"
    version = "2.0.0"
    datasets = {
        "demand": "silver.energy.demand",
        "pv": "silver.energy.production",
    }

    async def run(
        self,
        config: BatterySizingConfig,
        context,
    ) -> BatterySizingResult:
        total_demand = config.demand.total()
        total_pv = config.pv.total()

        capacity = min(config.max_capacity_kwh, total_pv)
        grid_import = max(0.0, total_demand - total_pv)
        sc = min(1.0, total_pv / total_demand) if total_demand else 0.0

        return BatterySizingResult(
            capacity_kwh=capacity,
            grid_import_kwh=grid_import,
            self_consumption_ratio=sc,
        )
