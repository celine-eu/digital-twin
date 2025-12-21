from __future__ import annotations

import math
import pandas as pd


def annualize_equiv(value: float, days: float) -> float:
    # PoC: convert period value to yearly equivalent
    if days <= 0:
        return value
    return value * (365.0 / days)


def compute_candidate_metrics(
    base_df: pd.DataFrame,
    sim_df: pd.DataFrame,
    *,
    period_days: float,
    import_price_col: str = "import_price_eur_per_kwh",
    export_price_col: str = "export_price_eur_per_kwh",
) -> dict:
    # baseline
    load = base_df["load_kw"].clip(lower=0)
    pv = base_df["pv_kw"].clip(lower=0)
    pv_to_load = pd.concat([pv, load], axis=1).min(axis=1)
    base_sc = float(pv_to_load.sum() / pv.sum()) if float(pv.sum()) > 0 else 0.0

    # after
    pv_to_load_after = sim_df["pv_to_load_after"]
    after_sc = float(pv_to_load_after.sum() / pv.sum()) if float(pv.sum()) > 0 else 0.0

    # costs
    base_import = (load - pv).clip(lower=0)
    base_export = (pv - load).clip(lower=0)
    base_cost = float((base_import * base_df[import_price_col]).sum() - (base_export * base_df[export_price_col]).sum())

    sim_import = sim_df["net_import_kw"]
    sim_export = sim_df["net_export_kw"]
    sim_cost = float((sim_import * sim_df[import_price_col]).sum() - (sim_export * sim_df[export_price_col]).sum())

    savings = base_cost - sim_cost  # positive means better
    annual_savings = annualize_equiv(savings, period_days)

    return {
        "self_consumption_ratio_delta": after_sc - base_sc,
        "annual_savings_eur_equiv": annual_savings,
    }


def simple_payback(capex: float, annual_savings: float) -> float | None:
    if annual_savings <= 0:
        return None
    return capex / annual_savings


def npv(capex: float, annual_savings: float, discount_rate: float, lifetime_years: int) -> float:
    r = max(0.0, float(discount_rate))
    n = int(lifetime_years)
    if r == 0:
        return -capex + annual_savings * n
    return -capex + sum(annual_savings / ((1 + r) ** t) for t in range(1, n + 1))
