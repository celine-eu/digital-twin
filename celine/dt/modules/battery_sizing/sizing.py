from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from celine.dt.modules.battery_sizing.models import BatterySizingInputs, BatterySizingResult

logger = logging.getLogger(__name__)


@dataclass
class _SimKPIs:
    grid_import: float
    grid_export: float
    pv_used_locally: float
    demand_met_locally: float
    battery_throughput: float


def _simulate(
    *,
    demand_kwh: list[float],
    pv_kwh: list[float],
    dt_h: float,
    capacity_kwh: float,
    power_kw: float,
    rte: float,
) -> _SimKPIs:
    """Simple energy-flow simulation (PV -> load -> battery -> grid)."""
    if capacity_kwh <= 0 or power_kw <= 0:
        raise ValueError("capacity_kwh and power_kw must be positive")

    # Split losses between charge/discharge
    eta_c = math.sqrt(rte)
    eta_d = math.sqrt(rte)

    soc = 0.0  # kWh, start empty (conservative)

    grid_import = 0.0
    grid_export = 0.0
    pv_used_locally = 0.0
    demand_met_locally = 0.0
    battery_throughput = 0.0

    max_energy_per_step = power_kw * dt_h  # kWh per step

    for d, pv in zip(demand_kwh, pv_kwh):
        # PV directly to demand
        direct = min(d, pv)
        pv_used_locally += direct
        demand_met_locally += direct

        remaining_demand = d - direct
        excess_pv = pv - direct

        # Charge from excess PV
        if excess_pv > 0:
            charge_in = min(excess_pv, max_energy_per_step)  # kWh into charger
            stored = charge_in * eta_c
            space = capacity_kwh - soc
            stored_eff = min(stored, space)
            charge_in_used = stored_eff / eta_c if eta_c > 0 else 0.0

            soc += stored_eff
            battery_throughput += stored_eff

            grid_export += max(0.0, excess_pv - charge_in_used)

        # Discharge to meet remaining demand
        if remaining_demand > 0 and soc > 0:
            discharge_out = min(remaining_demand, max_energy_per_step)  # kWh at load
            required_from_soc = discharge_out / eta_d if eta_d > 0 else discharge_out
            actual_from_soc = min(required_from_soc, soc)
            actual_to_load = actual_from_soc * eta_d

            soc -= actual_from_soc
            demand_met_locally += actual_to_load
            battery_throughput += actual_from_soc

            remaining_demand -= actual_to_load

        # Grid import
        if remaining_demand > 0:
            grid_import += remaining_demand

    return _SimKPIs(
        grid_import=grid_import,
        grid_export=grid_export,
        pv_used_locally=pv_used_locally,
        demand_met_locally=demand_met_locally,
        battery_throughput=battery_throughput,
    )


def size_battery_simple(inputs: BatterySizingInputs) -> BatterySizingResult:
    """Brute-force capacity sweep with a pragmatic objective."""
    total_demand = float(sum(inputs.demand_kwh))
    total_pv = float(sum(inputs.pv_kwh))

    if total_demand <= 0:
        return BatterySizingResult(
            capacity_kwh=0.0,
            power_kw=0.0,
            total_demand_kwh=total_demand,
            total_pv_kwh=total_pv,
            grid_import_kwh=0.0,
            grid_export_kwh=total_pv,
            self_consumption_ratio=0.0,
            self_sufficiency_ratio=0.0,
            battery_throughput_kwh=0.0,
            equivalent_full_cycles=0.0,
        )

    best: tuple[float, float, _SimKPIs] | None = None

    cap = inputs.capacity_step_kwh
    while cap <= inputs.max_capacity_kwh + 1e-9:
        power = cap * inputs.c_rate
        if inputs.max_power_kw is not None:
            power = min(power, inputs.max_power_kw)
        power = max(power, 0.1)

        kpis = _simulate(
            demand_kwh=inputs.demand_kwh,
            pv_kwh=inputs.pv_kwh,
            dt_h=inputs.timestep_hours,
            capacity_kwh=cap,
            power_kw=power,
            rte=inputs.roundtrip_efficiency,
        )

        sc = (kpis.pv_used_locally / total_pv) if total_pv > 0 else 0.0

        if best is None:
            best = (cap, power, kpis)
        else:
            best_cap, best_pow, best_kpis = best
            best_sc = (best_kpis.pv_used_locally / total_pv) if total_pv > 0 else 0.0

            def meets_target(x: float) -> int:
                return 1 if x >= inputs.target_self_consumption else 0

            candidate = (kpis.grid_import, -meets_target(sc), -sc, cap)
            incumbent = (best_kpis.grid_import, -meets_target(best_sc), -best_sc, best_cap)

            if candidate < incumbent:
                best = (cap, power, kpis)

        cap += inputs.capacity_step_kwh

    assert best is not None
    best_cap, best_pow, best_kpis = best

    self_consumption = (best_kpis.pv_used_locally / total_pv) if total_pv > 0 else 0.0
    self_sufficiency = best_kpis.demand_met_locally / total_demand if total_demand > 0 else 0.0
    cycles = (best_kpis.battery_throughput / best_cap) if best_cap > 0 else 0.0

    return BatterySizingResult(
        capacity_kwh=float(round(best_cap, 6)),
        power_kw=float(round(best_pow, 6)),
        total_demand_kwh=total_demand,
        total_pv_kwh=total_pv,
        grid_import_kwh=float(best_kpis.grid_import),
        grid_export_kwh=float(best_kpis.grid_export),
        self_consumption_ratio=float(self_consumption),
        self_sufficiency_ratio=float(self_sufficiency),
        battery_throughput_kwh=float(best_kpis.battery_throughput),
        equivalent_full_cycles=float(cycles),
    )
