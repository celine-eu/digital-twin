from __future__ import annotations

import pandas as pd


def compute_baseline_kpis(df: pd.DataFrame) -> dict:
    # df: columns load_kw, pv_kw, import_price_eur_per_kwh, export_price_eur_per_kwh
    load = df["load_kw"].clip(lower=0)
    pv = df["pv_kw"].clip(lower=0)

    pv_to_load = pd.concat([pv, load], axis=1).min(axis=1)
    import_kw = (load - pv).clip(lower=0)
    export_kw = (pv - load).clip(lower=0)

    total_pv = float(pv.sum())
    total_load = float(load.sum())

    self_consumption_ratio = float(pv_to_load.sum() / total_pv) if total_pv > 0 else 0.0
    self_sufficiency_ratio = float(pv_to_load.sum() / total_load) if total_load > 0 else 0.0

    # Costs (PoC): assume timestep already accounts for kWh equivalence if 1-hour. If 15m, user should scale.
    # To keep the PoC consistent, we compute "energy units" in "kWh-equivalent per row" by assuming dt_hours=1.
    # Apps can override or the materializer can add dt_hours.
    import_cost = float((import_kw * df["import_price_eur_per_kwh"]).sum())
    export_revenue = float((export_kw * df["export_price_eur_per_kwh"]).sum())

    return {
        "self_consumption_ratio": self_consumption_ratio,
        "self_sufficiency_ratio": self_sufficiency_ratio,
        "total_pv_kwh_equiv": total_pv,
        "total_load_kwh_equiv": total_load,
        "import_kwh_equiv": float(import_kw.sum()),
        "export_kwh_equiv": float(export_kw.sum()),
        "import_cost_eur_equiv": import_cost,
        "export_revenue_eur_equiv": export_revenue,
    }
