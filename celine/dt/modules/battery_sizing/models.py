from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class BatterySizingInputs(BaseModel):
    """Inputs for the battery sizing app.

    demand_kwh and pv_kwh are energy per time-step in kWh (same length).
    """

    demand_kwh: List[float] = Field(..., min_length=1)
    pv_kwh: List[float] = Field(..., min_length=1)

    timestep_hours: float = Field(default=1.0, gt=0.0)
    roundtrip_efficiency: float = Field(default=0.92, gt=0.0, le=1.0)

    # Search space
    max_capacity_kwh: float = Field(default=200.0, gt=0.0)
    capacity_step_kwh: float = Field(default=5.0, gt=0.0)

    # Power derived from capacity via C-rate: power_kw = c_rate * capacity_kwh
    c_rate: float = Field(default=0.5, gt=0.0)

    # Soft target (best effort)
    target_self_consumption: float = Field(default=0.80, gt=0.0, le=1.0)

    # Optional hard power cap (e.g. inverter limit)
    max_power_kw: Optional[float] = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _check_lengths(self) -> "BatterySizingInputs":
        if len(self.demand_kwh) != len(self.pv_kwh):
            raise ValueError("demand_kwh and pv_kwh must have the same length")
        return self

    @field_validator("demand_kwh", "pv_kwh")
    @classmethod
    def _non_negative(cls, v: List[float]) -> List[float]:
        if any(x < 0 for x in v):
            raise ValueError("Series values must be non-negative")
        return v


class BatterySizingResult(BaseModel):
    capacity_kwh: float
    power_kw: float

    total_demand_kwh: float
    total_pv_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float

    self_consumption_ratio: float  # PV used locally / PV generated
    self_sufficiency_ratio: float  # demand met locally / demand

    battery_throughput_kwh: float
    equivalent_full_cycles: float
