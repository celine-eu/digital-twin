from __future__ import annotations

from fastapi.testclient import TestClient
from celine.dt.main import create_app


def test_list_apps_includes_battery_sizing() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/apps")
    assert resp.status_code == 200
    apps = resp.json()

    assert any(a["key"] == "battery-sizing" for a in apps)
    bs = next(a for a in apps if a["key"] == "battery-sizing")
    assert "version" in bs


def test_describe_battery_sizing_has_schemas() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/apps/battery-sizing/describe")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["key"] == "battery-sizing"
    assert data["input_schema"] is not None
    assert data["output_schema"] is not None

    # sanity check schema contains expected fields
    props = data["input_schema"]["properties"]
    assert "demand" in props
    assert "pv" in props
