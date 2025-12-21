from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_battery_dispatch(
    df: pd.DataFrame,
    *,
    capacity_kwh: float,
    power_kw: float,
    round_trip_efficiency: float,
) -> pd.DataFrame:
    # NOTE: PoC assumes each row is 1 "kWh-equivalent time step". For real, include dt_hours.
    # Treat load_kw/pv_kw as energy per step for KPI deltas; the relative comparisons still hold if uniform.
    load = df["load_kw"].to_numpy(dtype=float)
    pv = df["pv_kw"].to_numpy(dtype=float)

    soc = 0.0
    soc_series = np.zeros(len(df), dtype=float)
    charge = np.zeros(len(df), dtype=float)
    discharge = np.zeros(len(df), dtype=float)

    eta = float(round_trip_efficiency)
    # split to charge/discharge sqrt for symmetric loss
    eta_c = np.sqrt(eta)
    eta_d = np.sqrt(eta)

    for i in range(len(df)):
        net = load[i] - pv[i]  # >0 needs import, <0 surplus
        if net > 0:
            # discharge to reduce import
            d = min(power_kw, net, soc)  # discharge energy per step
            soc -= d
            discharge[i] = d * eta_d  # effective delivered to load after losses
        else:
            # charge with surplus
            surplus = -net
            c = min(power_kw, surplus, capacity_kwh - soc)
            soc += c * eta_c  # store after losses
            charge[i] = c

        soc = max(0.0, min(capacity_kwh, soc))
        soc_series[i] = soc

    out = df.copy()
    # Effective PV to load increases by discharge; effective export decreases by charging.
    out["battery_soc_kwh"] = soc_series
    out["battery_charge_kw"] = charge
    out["battery_discharge_kw"] = discharge

    # Adjusted net after battery
    # net_import = max(load - pv - discharge, 0)
    # net_export = max(pv - load - charge, 0)  (charge consumes surplus)
    out["net_import_kw"] = (out["load_kw"] - out["pv_kw"] - out["battery_discharge_kw"]).clip(lower=0.0)
    out["net_export_kw"] = (out["pv_kw"] - out["load_kw"] - out["battery_charge_kw"]).clip(lower=0.0)

    # self-consumed PV after battery = min(pv, load) + discharge (bounded by remaining load)
    base_pv_to_load = pd.concat([out["pv_kw"], out["load_kw"]], axis=1).min(axis=1)
    remaining_load = (out["load_kw"] - base_pv_to_load).clip(lower=0.0)
    extra = pd.concat([remaining_load, out["battery_discharge_kw"]], axis=1).min(axis=1)
    out["pv_to_load_after"] = base_pv_to_load + extra

    return out
