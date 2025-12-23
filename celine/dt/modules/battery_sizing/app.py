from __future__ import annotations

import logging
from typing import Any, Mapping

from celine.dt.modules.battery_sizing.models import BatterySizingInputs, BatterySizingResult
from celine.dt.modules.battery_sizing.sizing import size_battery_simple

logger = logging.getLogger(__name__)


class BatterySizingApp:
    key = "battery-sizing"
    version = "1.0.0"

    async def run(self, inputs: Any, **context: Any) -> dict:
        if isinstance(inputs, BatterySizingInputs):
            parsed = inputs
        elif isinstance(inputs, Mapping):
            parsed = BatterySizingInputs.model_validate(inputs)
        else:
            raise TypeError("inputs must be a dict-like object or BatterySizingInputs")

        logger.info(
            "Battery sizing run: steps=%s dt_h=%s target_sc=%.3f",
            len(parsed.demand_kwh),
            parsed.timestep_hours,
            parsed.target_self_consumption,
        )

        res: BatterySizingResult = size_battery_simple(parsed)
        return res.model_dump()
