# tests/unit/simulation/test_kpis.py
import pandas as pd
from celine.dt.simulation.kpis import compute_baseline_kpis


def test_compute_baseline_kpis_basic():
    df = pd.DataFrame(
        {
            "load_kw": [10, 10],
            "pv_kw": [5, 15],
            "import_price_eur_per_kwh": [0.2, 0.2],
            "export_price_eur_per_kwh": [0.1, 0.1],
        }
    )

    kpis = compute_baseline_kpis(df)

    assert kpis["total_load_kwh_equiv"] == 20
    assert kpis["total_pv_kwh_equiv"] == 20
    assert 0 <= kpis["self_consumption_ratio"] <= 1
