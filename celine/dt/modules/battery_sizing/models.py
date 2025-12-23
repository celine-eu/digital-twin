from __future__ import annotations
from pydantic import BaseModel, Field
from celine.dt.core.timeseries import TimeSeries


class BatterySizingResult(BaseModel):
    capacity_kwh: float
    grid_import_kwh: float
    self_consumption_ratio: float


class BatterySizingConfig(BaseModel):
    demand: TimeSeries[float]
    pv: TimeSeries[float]
    roundtrip_efficiency: float = Field(default=0.92, gt=0, le=1)
    max_capacity_kwh: float = Field(default=200, gt=0)
    capacity_step_kwh: float = Field(default=5, gt=0)
