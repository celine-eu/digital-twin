from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lon: float


ChargingIndicator = Literal["OPTIMAL", "MARGINAL", "SUBOPTIMAL", "UNSTABLE"]


class EVChargingReadinessConfig(BaseModel):
    """Configuration for the EV Charging Readiness app.

    Notes:
      - This app is *decision-oriented*: it transforms forecasts into an operational signal.
      - It intentionally uses simple, explainable heuristics (no hidden ML).
    """

    community_id: str = Field(..., description="Logical identifier of the energy community")
    location: Location = Field(..., description="Reference point for forecast selection")

    # Data selection
    window_hours: int = Field(24, ge=1, le=168, description="Decision window horizon")
    start_utc: Optional[datetime] = Field(
        default=None,
        description="Optional start time (UTC). Defaults to context.now.",
    )

    # Community context
    pv_capacity_kw: float = Field(..., gt=0, description="Installed PV capacity (kW)")
    ev_charging_capacity_kw: float = Field(
        ..., gt=0, description="Max aggregate EV charging power (kW)"
    ) 

    weather_location_id: Optional[str] = Field(
        default=None,
        description="Optional location_id to filter hourly weather rows (recommended).",
    )

    # Thresholds / tuning (kept explicit for explainability)
    optimal_ratio: float = Field(
        0.8, ge=0, le=2, description="PV/EV ratio threshold for OPTIMAL"
    )
    marginal_ratio: float = Field(
        0.4, ge=0, le=2, description="PV/EV ratio threshold for MARGINAL"
    )
    unstable_confidence: float = Field(
        0.5, ge=0, le=1, description="Below this confidence we output UNSTABLE"
    )


class EVChargingReadinessResult(BaseModel):
    """Decision-ready indicator for EV charging using community PV."""

    community_id: str
    start_utc: datetime
    end_utc: datetime
    window_hours: int

    expected_pv_kwh: float
    ev_charging_capacity_kwh: float

    indicator: ChargingIndicator
    confidence: float

    # Explanations
    drivers: list[str] = []
    recommendations: list[str] = []

    # Debug-friendly details (safe to expose, useful in demos)
    mean_clouds_pct: float
    clouds_std_pct: float
    solar_energy_kwh_per_m2_total: float
    pv_ev_ratio: float


