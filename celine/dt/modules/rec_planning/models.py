"""Pydantic models for the REC planning simulation.

The intent is to keep these models stable and transport-agnostic:
- ScenarioConfig: defines the expensive data boundary (time range, community, resolution)
- Scenario: contains cached inputs + baseline metrics (materialized in a workspace)
- Parameters: cheap what-if knobs (PV size, battery size, financial assumptions, etc.)
- Result: computed metrics for a run
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Resolution = Literal["15min", "1h", "1d"]


# ─────────────────────────────────────────────────────────────────────────────
# Scenario Configuration (input to build_scenario)
# ─────────────────────────────────────────────────────────────────────────────


class RECScenarioConfig(BaseModel):
    """Configuration for building a REC planning scenario.

    This defines the expensive data boundary - what data to fetch and cache.
    """

    community_id: str = Field(..., description="REC identifier / boundary.")
    reference_start: datetime = Field(
        ..., description="Start of the reference period (inclusive)."
    )
    reference_end: datetime = Field(
        ..., description="End of the reference period (exclusive)."
    )
    resolution: Resolution = Field(
        "1h", description="Time resolution for the simulation."
    )
    timezone: str = Field("Europe/Rome", description="Timezone for the time series.")

    # Optional: narrow/override scope
    boundary: dict[str, Any] | None = Field(
        default=None,
        description="Optional boundary selector (participants/assets/etc.).",
    )
    dataset_id: str | None = Field(
        default=None,
        description="Optional dataset ID for data fetching.",
    )
    assumptions: dict[str, Any] | None = Field(
        default=None,
        description="Optional assumptions (location, existing_pv_kwp, etc.).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario (output of build_scenario, cached)
# ─────────────────────────────────────────────────────────────────────────────


class RECScenario(BaseModel):
    """Built scenario containing cached data and baseline metrics.

    This is the expensive, cacheable result of build_scenario().
    """

    # Identity (scenario_id is assigned by the service after build)
    scenario_id: str = Field(default="", description="Assigned by scenario service.")
    community_id: str

    # Configuration echo
    boundary: dict[str, Any] | None = None
    dataset_id: str | None = None
    reference_start: datetime
    reference_end: datetime
    resolution: Resolution

    # Baseline metrics (computed once during scenario build)
    baseline_total_consumption_kwh: float = 0.0
    baseline_total_generation_kwh: float = 0.0
    baseline_self_consumed_kwh: float = 0.0
    baseline_self_consumption_ratio: float = 0.0
    baseline_self_sufficiency_ratio: float = 0.0
    baseline_grid_import_kwh: float = 0.0
    baseline_grid_export_kwh: float = 0.0
    baseline_incentive_eur: float = 0.0

    # Workspace artifact paths
    artifacts: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Parameters (cheap what-if knobs)
# ─────────────────────────────────────────────────────────────────────────────


class RECPlanningParameters(BaseModel):
    """Parameters for a simulation run.

    These are the cheap what-if knobs that can be varied without rebuilding
    the scenario.
    """

    # PV additions
    pv_kwp: float = Field(
        default=0.0, ge=0.0, description="Additional PV capacity (kWp) to simulate."
    )
    pv_tilt: float = Field(
        default=30.0, ge=0.0, le=90.0, description="PV panel tilt angle (degrees)."
    )
    pv_azimuth: float = Field(
        default=180.0,
        ge=0.0,
        le=360.0,
        description="PV panel azimuth (degrees, 180=south).",
    )
    pv_profile: str | None = Field(
        default=None,
        description="Optional named PV profile in workspace (parquet key).",
    )

    # Battery additions
    battery_kwh: float = Field(
        default=0.0, ge=0.0, description="Battery capacity (kWh) to simulate."
    )
    battery_power_kw: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional battery power limit (kW). Defaults to capacity/2.",
    )

    # Financial parameters
    pv_cost_eur_per_kwp: float = Field(
        default=1200.0, ge=0.0, description="PV installation cost (EUR/kWp)."
    )
    battery_cost_eur_per_kwh: float = Field(
        default=500.0, ge=0.0, description="Battery installation cost (EUR/kWh)."
    )
    electricity_price_eur_kwh: float = Field(
        default=0.25, ge=0.0, description="Grid electricity price (EUR/kWh)."
    )
    feed_in_tariff_eur_kwh: float = Field(
        default=0.05,
        ge=0.0,
        description="Feed-in tariff for exported energy (EUR/kWh).",
    )
    rec_incentive_eur_kwh: float = Field(
        default=0.11, ge=0.0, description="REC incentive for shared energy (EUR/kWh)."
    )

    # Economic analysis parameters
    discount_rate: float = Field(
        default=0.05, ge=0.0, le=1.0, description="Discount rate for NPV calculation."
    )
    project_lifetime_years: int = Field(
        default=25,
        ge=1,
        le=50,
        description="Project lifetime for economic analysis (years).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────


class Recommendation(BaseModel):
    """A recommendation from the simulation."""

    category: str = Field(
        ..., description="Category: sizing, economics, operations, error"
    )
    message: str = Field(..., description="Human-readable recommendation")
    priority: Literal["high", "medium", "low"] = "medium"
    pv_kwp: float = Field(0.0, ge=0.0, description="Recommended PV capacity (kWp)")
    battery_kwh: float = Field(
        0.0, ge=0.0, description="Recommended battery capacity (kWh)"
    )
    rationale: str = Field("", description="Explanation for the recommendation")


class RECPlanningResult(BaseModel):
    """Result of a REC planning simulation run.

    Contains baseline metrics, with-investment metrics, deltas, and recommendations.
    The simulation constructs these as dicts, so we use dict[str, Any] for flexibility.
    """

    # Baseline (from scenario) - dict with energy metrics
    baseline: dict[str, Any] = Field(
        default_factory=dict, description="Baseline energy metrics from scenario"
    )

    # With investment (computed) - dict with energy + economic metrics
    with_investment: dict[str, Any] = Field(
        default_factory=dict, description="Metrics with the proposed investment applied"
    )

    # Delta from baseline - dict with delta metrics
    delta: dict[str, Any] = Field(
        default_factory=dict,
        description="Difference between with_investment and baseline",
    )

    # Recommendation (single string or Recommendation object)
    recommendation: str | Recommendation | None = Field(
        default=None, description="Investment recommendation"
    )

    # Legacy fields for backward compatibility with older API consumers
    self_consumption_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    incentive_eur: float = 0.0
    delta_self_consumption_kwh: float | None = None
    delta_incentive_eur: float | None = None
