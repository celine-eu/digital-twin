# celine/dt/modules/energy_balance/components.py
"""
Energy Balance components.

Pure computation components for energy balance calculations.
These are the core building blocks used by Apps and Simulations.
"""
from __future__ import annotations

from typing import Any, ClassVar, Type

from pydantic import BaseModel, Field
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Input/Output Models
# ─────────────────────────────────────────────────────────────────────────────


class EnergyBalanceInput(BaseModel):
    """Input for energy balance calculation."""

    generation_kwh: list[float] = Field(
        ...,
        description="Time series of generation in kWh (e.g., hourly)",
    )
    consumption_kwh: list[float] = Field(
        ...,
        description="Time series of consumption in kWh (same resolution as generation)",
    )
    timestamps: list[str] | None = Field(
        default=None,
        description="Optional ISO timestamps for each data point",
    )


class EnergyBalanceOutput(BaseModel):
    """Output of energy balance calculation."""

    # Core metrics
    self_consumption_ratio: float = Field(
        ...,
        ge=0,
        le=1,
        description="Ratio of generation consumed locally (0-1)",
    )
    self_sufficiency_ratio: float = Field(
        ...,
        ge=0,
        le=1,
        description="Ratio of consumption covered by local generation (0-1)",
    )

    # Energy totals
    total_generation_kwh: float = Field(..., description="Total generation in kWh")
    total_consumption_kwh: float = Field(..., description="Total consumption in kWh")
    self_consumed_kwh: float = Field(
        ..., description="Energy consumed from local generation"
    )
    grid_import_kwh: float = Field(..., description="Energy imported from grid")
    grid_export_kwh: float = Field(..., description="Energy exported to grid")

    # Time series (optional, for detailed analysis)
    hourly_self_consumed: list[float] | None = Field(
        default=None,
        description="Hourly self-consumed energy",
    )
    hourly_grid_import: list[float] | None = Field(
        default=None,
        description="Hourly grid import",
    )
    hourly_grid_export: list[float] | None = Field(
        default=None,
        description="Hourly grid export",
    )


class AggregatedBalanceInput(BaseModel):
    """Input for aggregating multiple energy balances (e.g., community)."""

    balances: list[EnergyBalanceOutput] = Field(
        ...,
        description="Individual energy balances to aggregate",
    )
    sharing_enabled: bool = Field(
        default=True,
        description="Whether energy sharing within the group is enabled",
    )


class AggregatedBalanceOutput(BaseModel):
    """Output of aggregated energy balance."""

    # Individual totals
    total_generation_kwh: float
    total_consumption_kwh: float

    # Without sharing (sum of individual metrics)
    individual_self_consumed_kwh: float
    individual_self_consumption_ratio: float
    individual_self_sufficiency_ratio: float

    # With sharing (community-level optimization)
    shared_self_consumed_kwh: float
    shared_self_consumption_ratio: float
    shared_self_sufficiency_ratio: float

    # Sharing benefit
    sharing_benefit_kwh: float = Field(
        ...,
        description="Additional self-consumption enabled by sharing",
    )
    sharing_benefit_ratio: float = Field(
        ...,
        description="Improvement in self-consumption from sharing (0-1)",
    )

    # Grid interaction
    grid_import_kwh: float
    grid_export_kwh: float


# ─────────────────────────────────────────────────────────────────────────────
# Components
# ─────────────────────────────────────────────────────────────────────────────


class EnergyBalanceComponent:
    """
    Calculate energy balance metrics for a single entity.

    This component computes self-consumption and self-sufficiency ratios
    from generation and consumption time series.

    Self-consumption = self_consumed / total_generation
    Self-sufficiency = self_consumed / total_consumption

    Where self_consumed = min(generation, consumption) at each timestep.
    """

    key: ClassVar[str] = "energy-balance.calculator"
    version: ClassVar[str] = "1.0.0"

    input_type: Type[EnergyBalanceInput] = EnergyBalanceInput
    output_type: Type[EnergyBalanceOutput] = EnergyBalanceOutput

    async def compute(
        self,
        input: EnergyBalanceInput,
        context: Any,
    ) -> EnergyBalanceOutput:
        """Calculate energy balance metrics."""

        gen = np.array(input.generation_kwh)
        cons = np.array(input.consumption_kwh)

        if len(gen) != len(cons):
            raise ValueError(
                f"Generation ({len(gen)}) and consumption ({len(cons)}) "
                "must have same length"
            )

        # Calculate per-timestep values
        self_consumed = np.minimum(gen, cons)
        grid_import = np.maximum(cons - gen, 0)
        grid_export = np.maximum(gen - cons, 0)

        # Totals
        total_gen = float(np.sum(gen))
        total_cons = float(np.sum(cons))
        total_self_consumed = float(np.sum(self_consumed))
        total_import = float(np.sum(grid_import))
        total_export = float(np.sum(grid_export))

        # Ratios (handle division by zero)
        self_consumption_ratio = (
            total_self_consumed / total_gen if total_gen > 0 else 0.0
        )
        self_sufficiency_ratio = (
            total_self_consumed / total_cons if total_cons > 0 else 0.0
        )

        return EnergyBalanceOutput(
            self_consumption_ratio=self_consumption_ratio,
            self_sufficiency_ratio=self_sufficiency_ratio,
            total_generation_kwh=total_gen,
            total_consumption_kwh=total_cons,
            self_consumed_kwh=total_self_consumed,
            grid_import_kwh=total_import,
            grid_export_kwh=total_export,
            hourly_self_consumed=self_consumed.tolist(),
            hourly_grid_import=grid_import.tolist(),
            hourly_grid_export=grid_export.tolist(),
        )


class AggregatedBalanceComponent:
    """
    Aggregate energy balances for a group (e.g., energy community).

    Calculates both individual metrics (no sharing) and shared metrics
    (with internal energy sharing), showing the benefit of the community.
    """

    key: ClassVar[str] = "energy-balance.aggregator"
    version: ClassVar[str] = "1.0.0"

    input_type: Type[AggregatedBalanceInput] = AggregatedBalanceInput
    output_type: Type[AggregatedBalanceOutput] = AggregatedBalanceOutput

    async def compute(
        self,
        input: AggregatedBalanceInput,
        context: Any,
    ) -> AggregatedBalanceOutput:
        """Aggregate energy balances."""

        if not input.balances:
            raise ValueError("At least one balance is required")

        # Sum individual metrics
        total_gen = sum(b.total_generation_kwh for b in input.balances)
        total_cons = sum(b.total_consumption_kwh for b in input.balances)
        individual_self_consumed = sum(b.self_consumed_kwh for b in input.balances)

        # Individual ratios (weighted average)
        individual_sc_ratio = (
            individual_self_consumed / total_gen if total_gen > 0 else 0.0
        )
        individual_ss_ratio = (
            individual_self_consumed / total_cons if total_cons > 0 else 0.0
        )

        if input.sharing_enabled and len(input.balances) > 1:
            # With sharing: aggregate time series and recalculate
            # This requires the hourly data
            if all(b.hourly_self_consumed is not None for b in input.balances):
                # Reconstruct generation and consumption time series
                all_gen = []
                all_cons = []

                for b in input.balances:
                    # Reconstruct from balance outputs
                    # gen = self_consumed + export
                    # cons = self_consumed + import
                    hourly_export = b.hourly_grid_export or []
                    hourly_import = b.hourly_grid_import or []
                    hourly_self = b.hourly_self_consumed or []

                    gen = [s + e for s, e in zip(hourly_self, hourly_export)]
                    cons = [s + i for s, i in zip(hourly_self, hourly_import)]

                    all_gen.append(gen)
                    all_cons.append(cons)

                # Sum across all members
                agg_gen = np.sum(all_gen, axis=0)
                agg_cons = np.sum(all_cons, axis=0)

                # Recalculate with sharing
                shared_self_consumed_arr = np.minimum(agg_gen, agg_cons)
                shared_self_consumed = float(np.sum(shared_self_consumed_arr))

                grid_import = float(np.sum(np.maximum(agg_cons - agg_gen, 0)))
                grid_export = float(np.sum(np.maximum(agg_gen - agg_cons, 0)))

            else:
                # Fallback: estimate from totals (less accurate)
                # Assume perfect internal matching
                shared_self_consumed = min(total_gen, total_cons)
                grid_import = max(total_cons - total_gen, 0)
                grid_export = max(total_gen - total_cons, 0)

        else:
            # No sharing: use individual sums
            shared_self_consumed = individual_self_consumed
            grid_import = sum(b.grid_import_kwh for b in input.balances)
            grid_export = sum(b.grid_export_kwh for b in input.balances)

        # Shared ratios
        shared_sc_ratio = shared_self_consumed / total_gen if total_gen > 0 else 0.0
        shared_ss_ratio = shared_self_consumed / total_cons if total_cons > 0 else 0.0

        # Sharing benefit
        sharing_benefit = shared_self_consumed - individual_self_consumed
        sharing_benefit_ratio = (
            sharing_benefit / individual_self_consumed
            if individual_self_consumed > 0
            else 0.0
        )

        return AggregatedBalanceOutput(
            total_generation_kwh=total_gen,
            total_consumption_kwh=total_cons,
            individual_self_consumed_kwh=individual_self_consumed,
            individual_self_consumption_ratio=individual_sc_ratio,
            individual_self_sufficiency_ratio=individual_ss_ratio,
            shared_self_consumed_kwh=shared_self_consumed,
            shared_self_consumption_ratio=shared_sc_ratio,
            shared_self_sufficiency_ratio=shared_ss_ratio,
            sharing_benefit_kwh=sharing_benefit,
            sharing_benefit_ratio=sharing_benefit_ratio,
            grid_import_kwh=grid_import,
            grid_export_kwh=grid_export,
        )
