from __future__ import annotations

from fastapi.testclient import TestClient
from celine.dt.main import create_app


def test_run_battery_sizing_app() -> None:
    app = create_app()
    client = TestClient(app)

    payload = {
        "demand": {"values": [5, 5, 5, 5], "timestep_hours": 1.0},
        "pv": {"values": [0, 10, 10, 0], "timestep_hours": 1.0},
        "roundtrip_efficiency": 0.9,
        "max_capacity_kwh": 20.0,
        "capacity_step_kwh": 5.0,
    }

    resp = client.post("/apps/battery-sizing/run", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["@type"] == "BatterySizingResult"
    assert data["capacityKWh"] >= 0.0
    assert "gridImportKWh" in data
    assert "selfConsumptionRatio" in data
