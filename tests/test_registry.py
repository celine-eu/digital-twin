# tests/unit/core/test_registry.py
from celine.dt.core.registry import AppRegistry


def test_registry_loads_apps(tmp_path):
    cfg = tmp_path / "apps.yaml"
    cfg.write_text(
        """
apps:
  - key: battery-sizing
    import: celine.dt.apps.battery_sizing.app:get_app
"""
    )

    r = AppRegistry()
    r.load_from_yaml(str(cfg))
    r.register_enabled_apps()

    assert "battery-sizing" in r.apps
