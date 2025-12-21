from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class BatterySizingScenario(BaseModel):
    # required for core runner
    start: datetime
    end: datetime

    # economics inputs
    discount_rate: float = Field(default=0.05, ge=0.0, le=0.5)
    lifetime_years: int = Field(default=12, ge=1, le=40)

    cost_per_kwh_eur: float = Field(default=220, ge=0)
    cost_per_kw_eur: float = Field(default=80, ge=0)
    installation_fixed_eur: float = Field(default=8000, ge=0)

    # battery grid
    capacity_kwh_candidates: List[float] = Field(default_factory=lambda: [50, 100, 200, 500, 1000])
    power_hours: float = Field(default=2.0, gt=0.1, le=24.0)
    round_trip_efficiency: float = Field(default=0.90, gt=0.0, le=1.0)

    # optional constraints
    max_simple_payback_years: Optional[float] = Field(default=None, gt=0)

    @field_validator("capacity_kwh_candidates")
    @classmethod
    def _sorted_unique(cls, v: List[float]) -> List[float]:
        out = sorted(set(float(x) for x in v if float(x) > 0))
        if not out:
            raise ValueError("capacity_kwh_candidates must contain at least one positive value")
        return out


class BatteryCandidateResult(BaseModel):
    capacity_kwh: float
    power_kw: float
    round_trip_efficiency: float
    capex_eur: float
    annual_savings_eur_equiv: float
    simple_payback_years: float | None
    self_consumption_ratio_delta: float


class BatterySizingResults(BaseModel):
    baseline: dict
    recommended: list[BatteryCandidateResult]
