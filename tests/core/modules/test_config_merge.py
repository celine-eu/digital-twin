from __future__ import annotations

from pathlib import Path

from celine.dt.core.modules.config import load_modules_config


def test_modules_config_merge_and_override(tmp_path: Path) -> None:
    """
    Later files override earlier ones.
    Files are loaded in sorted order.
    """

    a = tmp_path / "01_base.yaml"
    b = tmp_path / "02_override.yaml"

    a.write_text(
        """
modules:
  - name: battery-sizing
    version: ">=1.0.0"
    import: pkg.a:module
    enabled: true
ontology:
  active: base
""",
        encoding="utf-8",
    )

    b.write_text(
        """
modules:
  - name: battery-sizing
    version: ">=2.0.0"
    import: pkg.b:module
    enabled: false
ontology:
  active: override
""",
        encoding="utf-8",
    )

    cfg = load_modules_config([str(tmp_path / "*.yaml")])

    assert len(cfg.modules) == 1
    m = cfg.modules[0]

    assert m.name == "battery-sizing"
    assert m.version == ">=2.0.0"
    assert m.import_path == "pkg.b:module"
    assert m.enabled is False
    assert cfg.ontology_active == "override"
