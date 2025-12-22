# tests/unit/simulation/test_battery_simulation.py
import pandas as pd
from celine.dt.apps.battery_sizing.simulation import simulate_battery_dispatch


def test_battery_dispatch_shapes():
    df = pd.DataFrame(
        {
            "load_kw": [10, 10, 10],
            "pv_kw": [0, 20, 0],
        }
    )

    out = simulate_battery_dispatch(
        df,
        capacity_kwh=10,
        power_kw=5,
        round_trip_efficiency=0.9,
    )

    assert "battery_soc_kwh" in out
    assert out["battery_soc_kwh"].max() <= 10
