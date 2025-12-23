from celine.dt.core.runner import resolve_config
from celine.dt.modules.battery_sizing.app import BatterySizingApp
from celine.dt.modules.battery_sizing.models import BatterySizingConfig


def test_resolve_config_merges_defaults_and_payload():
    app = BatterySizingApp()

    defaults = {
        "roundtrip_efficiency": 0.95,
        "max_capacity_kwh": 100,
    }

    payload = {
        "roundtrip_efficiency": 0.9,
        "capacity_step_kwh": 10,
        "demand": {"values": [1, 1], "timestep_hours": 1},
        "pv": {"values": [2, 2], "timestep_hours": 1},
    }

    cfg = resolve_config(
        app=app,
        defaults=defaults,
        payload=payload,
    )

    assert isinstance(cfg, BatterySizingConfig)
    assert cfg.roundtrip_efficiency == 0.9  # payload overrides
    assert cfg.max_capacity_kwh == 100  # default applied
    assert cfg.capacity_step_kwh == 10
