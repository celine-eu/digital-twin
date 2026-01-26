# celine/dt/modules/rec_planning/simulation.py
"""REC Planning simulation.

This module provides a concrete example of the *scenario vs parameters* split:

- **Scenario**: expensive/cached inputs (timeseries, baselines, derived metrics)
- **Parameters**: cheap what-if knobs (additional PV/battery sizing, financial assumptions)

The scenario artifacts are stored in the simulation workspace (parquet preferred),
and results are returned via the simulation run API (run_id).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, Mapping

from pydantic import BaseModel

from celine.dt.contracts.simulation import DTSimulation
from celine.dt.modules.rec_planning.models import (
    RECPlanningParameters,
    RECPlanningResult,
    RECScenario,
    RECScenarioConfig,
    Recommendation,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Location:
    latitude: float
    longitude: float


class RECPlanningSimulation(
    DTSimulation[RECScenarioConfig, RECScenario, RECPlanningParameters, RECPlanningResult]
):
    """REC planning simulation (baseline + investment what-if)."""

    key: ClassVar[str] = "rec.rec-planning"
    version: ClassVar[str] = "0.1.0"

    scenario_config_type = RECScenarioConfig
    scenario_type = RECScenario
    parameters_type = RECPlanningParameters
    result_type = RECPlanningResult

    # ---------------------------------------------------------------------
    # Scenario build (expensive, cacheable)
    # ---------------------------------------------------------------------

    async def build_scenario(
        self,
        config: RECScenarioConfig,
        workspace: Any,
        context: Any,
    ) -> RECScenario:
        """Build and cache baseline artifacts for a community/boundary."""

        reference_start = config.reference_start
        reference_end = config.reference_end

        if reference_end <= reference_start:
            raise ValueError("reference_end must be after reference_start")

        # Resolution (only 1h, 15min, 1d supported by config schema)
        step = self._resolution_to_timedelta(config.resolution)
        num_steps = int((reference_end - reference_start) / step)

        assumptions = config.assumptions or {}
        location = self._parse_location(assumptions.get("location"))
        existing_pv_kwp = float(assumptions.get("existing_pv_kwp", 0.0))
        existing_battery_kwh = float(assumptions.get("existing_battery_kwh", 0.0))

        participant_ids = self._extract_participant_ids(config.boundary)
        num_participants = int(
            assumptions.get("num_participants", len(participant_ids) or 10)
        )
        annual_kwh_per_participant = float(
            assumptions.get("annual_kwh_per_participant", 4000.0)
        )

        logger.info(
            "Building REC scenario community=%s steps=%d res=%s participants=%d workspace=%s",
            config.community_id,
            num_steps,
            config.resolution,
            num_participants,
            getattr(workspace, "id", "?"),
        )

        # 1) Consumption baseline (synthetic fallback; production code should use context.values)
        consumption_kwh = self._generate_consumption_profile(
            num_steps=num_steps,
            num_participants=num_participants,
            annual_kwh_per_participant=annual_kwh_per_participant,
            step=step,
        )

        # 2) Generation baseline for existing PV (synthetic fallback; production code should use pvlib)
        generation_kwh = (
            self._generate_pv_profile(
                num_steps=num_steps,
                pv_kwp=existing_pv_kwp,
                location=location,
                step=step,
            )
            if existing_pv_kwp > 0
            else [0.0] * num_steps
        )

        # 3) Baseline energy accounting (very simplified)
        baseline_total_consumption_kwh = float(sum(consumption_kwh))
        baseline_total_generation_kwh = float(sum(generation_kwh))
        baseline_self_consumed_kwh = float(
            sum(min(c, g) for c, g in zip(consumption_kwh, generation_kwh))
        )

        baseline_self_consumption_ratio = (
            baseline_self_consumed_kwh / baseline_total_generation_kwh
            if baseline_total_generation_kwh > 0
            else 0.0
        )
        baseline_self_sufficiency_ratio = (
            baseline_self_consumed_kwh / baseline_total_consumption_kwh
            if baseline_total_consumption_kwh > 0
            else 0.0
        )

        # Persist artifacts
        artifacts: list[str] = []

        try:
            import pandas as pd

            idx = self._make_datetime_index(reference_start, num_steps, step)

            cdf = pd.DataFrame({"consumption_kwh": consumption_kwh}, index=idx)
            gdf = pd.DataFrame({"generation_kwh": generation_kwh}, index=idx)

            await workspace.write_parquet("baseline/consumption.parquet", cdf)
            await workspace.write_parquet("baseline/generation.parquet", gdf)
            artifacts += [
                "baseline/consumption.parquet",
                "baseline/generation.parquet",
            ]
        except Exception as exc:
            # JSON fallback (keeps demo runnable without pandas)
            logger.warning("Parquet write failed (%s). Falling back to JSON.", exc)
            await workspace.write_json(
                "baseline/consumption.json", {"consumption_kwh": consumption_kwh}
            )
            await workspace.write_json(
                "baseline/generation.json", {"generation_kwh": generation_kwh}
            )
            artifacts += [
                "baseline/consumption.json",
                "baseline/generation.json",
            ]

        scenario = RECScenario(
            community_id=config.community_id,
            boundary=config.boundary,
            dataset_id=config.dataset_id,
            reference_start=reference_start,
            reference_end=reference_end,
            resolution=config.resolution,
            baseline_total_consumption_kwh=baseline_total_consumption_kwh,
            baseline_total_generation_kwh=baseline_total_generation_kwh,
            baseline_self_consumed_kwh=baseline_self_consumed_kwh,
            baseline_self_consumption_ratio=baseline_self_consumption_ratio,
            baseline_self_sufficiency_ratio=baseline_self_sufficiency_ratio,
            artifacts=artifacts,
        )

        return scenario

    # ---------------------------------------------------------------------
    # Simulation run (fast, parameterized)
    # ---------------------------------------------------------------------

    async def simulate(
        self,
        scenario: RECScenario,
        parameters: RECPlanningParameters,
        context: Any,
    ) -> RECPlanningResult:
        """Apply parameters to cached scenario and compute metrics."""

        # Retrieve baseline series from workspace if available via context hook
        workspace = getattr(context, "workspace", None) or getattr(context, "_workspace", None)

        consumption_kwh, generation_kwh, step = await self._load_baseline_series(
            scenario, workspace
        )

        # Apply what-if additions
        # - parameters.pv_kwp represents *additional* PV capacity (kWp)
        # - parameters.battery_kwh represents *total* battery capacity to assume (kWh)
        add_pv_kwp = float(parameters.pv_kwp)
        total_battery_kwh = float(parameters.battery_kwh)

        # Synthetic PV production scaling relative to baseline PV
        # If baseline PV is 0, we still create a normalized PV curve.
        location = self._parse_location((scenario.boundary or {}).get("location"))  # optional
        add_generation_kwh = self._generate_pv_profile(
            num_steps=len(consumption_kwh),
            pv_kwp=max(add_pv_kwp, 0.0),
            location=location,
            step=step,
            tilt_deg=parameters.pv_tilt,
            azimuth_deg=parameters.pv_azimuth,
        )

        generation_kwh_whatif = [g + ag for g, ag in zip(generation_kwh, add_generation_kwh)]

        # Very simplified storage dispatch:
        # charge when generation > consumption, discharge when consumption > generation.
        self_consumed_kwh, shared_energy_kwh, grid_import_kwh = self._apply_storage_and_compute(
            consumption_kwh=consumption_kwh,
            generation_kwh=generation_kwh_whatif,
            battery_kwh=max(total_battery_kwh, 0.0),
        )

        total_consumption_kwh = float(sum(consumption_kwh))
        total_generation_kwh = float(sum(generation_kwh_whatif))

        self_consumption_ratio = (
            self_consumed_kwh / total_generation_kwh if total_generation_kwh > 0 else 0.0
        )
        self_sufficiency_ratio = (
            self_consumed_kwh / total_consumption_kwh if total_consumption_kwh > 0 else 0.0
        )

        # Financials (simple)
        investment_cost_eur = (
            max(add_pv_kwp, 0.0) * float(parameters.pv_cost_eur_per_kwp)
            + max(total_battery_kwh, 0.0) * float(parameters.battery_cost_eur_per_kwh)
        )

        # Annualized economics based on the modeled window
        window_hours = len(consumption_kwh) * (step.total_seconds() / 3600.0)
        window_year_fraction = window_hours / (365.0 * 24.0) if window_hours > 0 else 0.0

        # Savings: avoided grid import vs baseline (baseline grid import not stored; approximate via baseline ratios)
        baseline_grid_import_kwh = scenario.baseline_total_consumption_kwh - scenario.baseline_self_consumed_kwh
        delta_grid_import_kwh = float(baseline_grid_import_kwh - grid_import_kwh)

        savings_eur_window = delta_grid_import_kwh * float(parameters.electricity_price_eur_kwh)
        income_eur_window = shared_energy_kwh * float(parameters.rec_incentive_eur_kwh)

        annual_savings_eur = savings_eur_window / window_year_fraction if window_year_fraction > 0 else 0.0
        annual_income_eur = income_eur_window / window_year_fraction if window_year_fraction > 0 else 0.0

        simple_payback_years = (
            investment_cost_eur / (annual_savings_eur + annual_income_eur)
            if (annual_savings_eur + annual_income_eur) > 0
            else None
        )

        # NPV (very rough annuity approximation)
        npv_eur = self._npv(
            initial=-investment_cost_eur,
            annual_cashflow=annual_savings_eur + annual_income_eur,
            discount=float(parameters.discount_rate),
            years=int(parameters.project_lifetime_years),
        )

        with_investment = {
            "total_consumption_kwh": total_consumption_kwh,
            "total_generation_kwh": total_generation_kwh,
            "self_consumed_kwh": self_consumed_kwh,
            "self_consumption_ratio": self_consumption_ratio,
            "self_sufficiency_ratio": self_sufficiency_ratio,
            "shared_energy_kwh": shared_energy_kwh,
            "investment_cost_eur": investment_cost_eur,
            "annual_savings_eur": annual_savings_eur,
            "annual_income_eur": annual_income_eur,
            "simple_payback_years": simple_payback_years,
            "npv_eur": npv_eur,
            "total_pv_kwp": max(add_pv_kwp, 0.0),
            "total_battery_kwh": max(total_battery_kwh, 0.0),
        }

        delta = {
            "delta_self_consumption": self_consumption_ratio - scenario.baseline_self_consumption_ratio,
            "delta_self_sufficiency": self_sufficiency_ratio - scenario.baseline_self_sufficiency_ratio,
            "delta_grid_import_kwh": delta_grid_import_kwh,
        }

        recommendation = self._recommend(
            add_pv_kwp=add_pv_kwp,
            battery_kwh=total_battery_kwh,
            npv_eur=npv_eur,
            payback_years=simple_payback_years,
        )

        return RECPlanningResult(
            baseline={
                "total_consumption_kwh": scenario.baseline_total_consumption_kwh,
                "total_generation_kwh": scenario.baseline_total_generation_kwh,
                "self_consumed_kwh": scenario.baseline_self_consumed_kwh,
                "self_consumption_ratio": scenario.baseline_self_consumption_ratio,
                "self_sufficiency_ratio": scenario.baseline_self_sufficiency_ratio,
            },
            with_investment=with_investment,
            delta=delta,
            recommendation=recommendation,
        )

    def get_default_parameters(self) -> RECPlanningParameters:
        """Return sensible defaults for quick what-if exploration."""
        return RECPlanningParameters()


    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _resolution_to_timedelta(resolution: str) -> timedelta:
        if resolution == "15min":
            return timedelta(minutes=15)
        if resolution == "1d":
            return timedelta(days=1)
        # default 1h
        return timedelta(hours=1)

    @staticmethod
    def _make_datetime_index(start: datetime, n: int, step: timedelta):
        try:
            import pandas as pd
        except Exception:
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return pd.date_range(start=start, periods=n, freq=pd.Timedelta(step))

    @staticmethod
    def _parse_location(value: Any) -> _Location:
        # Accept dict with latitude/longitude; fallback to Trentino-ish coordinates.
        if isinstance(value, dict):
            lat = float(value.get("latitude", 46.05))
            lon = float(value.get("longitude", 11.23))
            return _Location(lat, lon)
        return _Location(46.05, 11.23)

    @staticmethod
    def _extract_participant_ids(boundary: Mapping[str, Any] | None) -> list[str]:
        if not boundary:
            return []
        ids = boundary.get("participant_ids") or boundary.get("participants") or []
        if isinstance(ids, list):
            return [str(x) for x in ids]
        return []

    async def _load_baseline_series(
        self,
        scenario: RECScenario,
        workspace: Any,
    ) -> tuple[list[float], list[float], timedelta]:
        step = self._resolution_to_timedelta(scenario.resolution)

        # If workspace is not available in context, we cannot reload artifacts.
        # Fall back to a flat series consistent with baseline totals.
        if workspace is None:
            n = max(int((scenario.reference_end - scenario.reference_start) / step), 1)
            c = [scenario.baseline_total_consumption_kwh / n] * n
            g = [scenario.baseline_total_generation_kwh / n] * n
            return c, g, step

        # Prefer parquet artifacts
        try:
            cdf = await workspace.read_parquet("baseline/consumption.parquet")
            gdf = await workspace.read_parquet("baseline/generation.parquet")
            consumption = [float(x) for x in cdf["consumption_kwh"].tolist()]
            generation = [float(x) for x in gdf["generation_kwh"].tolist()]
            return consumption, generation, step
        except Exception:
            pass

        # JSON fallback
        cjson = await workspace.read_json("baseline/consumption.json")
        gjson = await workspace.read_json("baseline/generation.json")
        consumption = [float(x) for x in cjson.get("consumption_kwh", [])]
        generation = [float(x) for x in gjson.get("generation_kwh", [])]
        return consumption, generation, step

    @staticmethod
    def _generate_consumption_profile(
        num_steps: int,
        num_participants: int,
        annual_kwh_per_participant: float,
        step: timedelta,
    ) -> list[float]:
        """Synthetic aggregate consumption profile with day/night seasonality."""
        if num_steps <= 0:
            return []

        # Convert annual consumption into per-step aggregate baseline
        hours_per_step = step.total_seconds() / 3600.0
        annual_steps = (365.0 * 24.0) / hours_per_step
        kwh_per_step_per_participant = annual_kwh_per_participant / annual_steps
        base = kwh_per_step_per_participant * num_participants

        out: list[float] = []
        for i in range(num_steps):
            # crude diurnal factor (peaks evening)
            hour = (i * hours_per_step) % 24.0
            if 17 <= hour <= 22:
                factor = 1.35
            elif 0 <= hour <= 6:
                factor = 0.75
            else:
                factor = 1.0
            out.append(base * factor)
        return out

    @staticmethod
    def _generate_pv_profile(
        num_steps: int,
        pv_kwp: float,
        location: _Location,
        step: timedelta,
        tilt_deg: float | None = None,
        azimuth_deg: float | None = None,
    ) -> list[float]:
        """Synthetic PV generation profile (placeholder for pvlib integration)."""
        if num_steps <= 0 or pv_kwp <= 0:
            return [0.0] * max(num_steps, 0)

        hours_per_step = step.total_seconds() / 3600.0

        out: list[float] = []
        for i in range(num_steps):
            hour = (i * hours_per_step) % 24.0
            # bell curve around solar noon
            if 6 <= hour <= 18:
                x = (hour - 12.0) / 6.0  # -1..1
                shape = max(0.0, 1.0 - x * x)  # parabola
            else:
                shape = 0.0

            # simple seasonal modulation by day-of-year
            day = int((i * hours_per_step) // 24) % 365
            season = 0.75 + 0.25 * (1.0 - abs(day - 172) / 172.0)  # peak around June 21

            # tilt/azimuth placeholders: keep as neutral multipliers for now
            tilt_factor = 1.0
            az_factor = 1.0
            out.append(pv_kwp * shape * season * hours_per_step * tilt_factor * az_factor * 0.2)
        return out

    @staticmethod
    def _apply_storage_and_compute(
        consumption_kwh: list[float],
        generation_kwh: list[float],
        battery_kwh: float,
    ) -> tuple[float, float, float]:
        """Return (self_consumed_kwh, shared_energy_kwh, grid_import_kwh)."""
        soc = 0.0
        self_consumed = 0.0
        shared = 0.0
        grid_import = 0.0

        for c, g in zip(consumption_kwh, generation_kwh):
            direct = min(c, g)
            self_consumed += direct
            c_rem = c - direct
            g_rem = g - direct

            # charge with surplus
            if g_rem > 0 and battery_kwh > 0:
                charge = min(g_rem, battery_kwh - soc)
                soc += charge
                g_rem -= charge

            # discharge to cover remaining consumption
            if c_rem > 0 and battery_kwh > 0 and soc > 0:
                discharge = min(c_rem, soc)
                soc -= discharge
                c_rem -= discharge
                self_consumed += discharge

            # remaining consumption is grid import
            if c_rem > 0:
                grid_import += c_rem

            # remaining generation can be shared/ exported
            if g_rem > 0:
                shared += g_rem

        return float(self_consumed), float(shared), float(grid_import)

    @staticmethod
    def _npv(initial: float, annual_cashflow: float, discount: float, years: int) -> float:
        if years <= 0:
            return initial
        d = max(discount, 0.0)
        npv = initial
        for t in range(1, years + 1):
            npv += annual_cashflow / ((1.0 + d) ** t)
        return float(npv)

    @staticmethod
    def _recommend(add_pv_kwp: float, battery_kwh: float, npv_eur: float, payback_years: float | None) -> Recommendation:
        if add_pv_kwp <= 0 and battery_kwh <= 0:
            return Recommendation(
                message="No investment scenario selected.",
                pv_kwp=0.0,
                battery_kwh=0.0,
                rationale="Parameters specify no additional PV/battery.",
            )

        if npv_eur > 0 and (payback_years is None or payback_years <= 10):
            return Recommendation(
                message="Investment appears attractive under current assumptions.",
                pv_kwp=float(max(add_pv_kwp, 0.0)),
                battery_kwh=float(max(battery_kwh, 0.0)),
                rationale="Positive NPV and acceptable payback.",
            )

        return Recommendation(
            message="Investment does not look attractive under current assumptions.",
            pv_kwp=float(max(add_pv_kwp, 0.0)),
            battery_kwh=float(max(battery_kwh, 0.0)),
            rationale="Negative NPV or excessive payback.",
        )


