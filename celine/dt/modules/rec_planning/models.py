# celine/dt/modules/rec_planning/models.py
"""Pydantic models for the REC planning simulation.

The intent is to keep these models stable and transport-agnostic:
- ScenarioConfig: defines the expensive data boundary (time range, community, resolution)
- Scenario: contains cached inputs + baseline metrics (materialized in a workspace)
- Parameters: cheap what-if knobs (PV size, battery size, etc.)
- Result: computed metrics for a run
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Resolution = Literal["15min", "1h", "1d"]


class RECScenarioConfig(BaseModel):
    community_id: str = Field(..., description="REC identifier / boundary.")
    reference_start: datetime = Field(..., description="Start of the reference period (inclusive).")
    reference_end: datetime = Field(..., description="End of the reference period (exclusive).")
    resolution: Resolution = Field("1h", description="Time resolution for the simulation.")
    timezone: str = Field("Europe/Rome", description="Timezone for the time series.")
    # Optional: narrow/override scope
    boundary: dict[str, Any] | None = Field(
        default=None,
        description="Optional boundary selector (participants/assets/etc.).",
    )


class RECScenario(BaseModel):
    scenario_id: str
    community_id: str
    reference_start: datetime
    reference_end: datetime
    resolution: Resolution

    # Baseline metrics (computed once during scenario build)
    baseline_self_consumption_kwh: float = 0.0
    baseline_grid_import_kwh: float = 0.0
    baseline_grid_export_kwh: float = 0.0
    baseline_incentive_eur: float = 0.0

    # Workspace pointers (materialized parquet paths, etc.)
    artifacts: dict[str, str] = Field(default_factory=dict)


class RECPlanningParameters(BaseModel):
    pv_kwp: float = Field(0.0, ge=0.0, description="Additional PV size (kWp) to simulate.")
    battery_kwh: float = Field(0.0, ge=0.0, description="Battery capacity (kWh) to simulate.")
    battery_power_kw: float | None = Field(
        default=None, ge=0.0, description="Optional battery power limit (kW)."
    )
    pv_profile: Optional[str] = Field(
        default=None, description="Optional named PV profile in workspace (parquet key)."
    )


class RECPlanningResult(BaseModel):
    self_consumption_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    incentive_eur: float

    # Comparisons to baseline (optional)
    delta_self_consumption_kwh: float | None = None
    delta_incentive_eur: float | None = None
