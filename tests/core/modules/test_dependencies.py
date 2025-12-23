import sys
import types
import pytest

from celine.dt.core.registry import DTRegistry
from celine.dt.core.modules.config import ModulesConfig, ModuleSpec, DependencySpec
from celine.dt.core.modules.loader import load_and_register_modules


class DummyModule:
    name = "battery"
    version = "1.0.0"

    def register(self, registry):
        pass


def test_missing_dependency_raises(monkeypatch) -> None:
    mod = types.ModuleType("fake.battery")
    mod.module = DummyModule()  # type: ignore
    sys.modules["fake.battery"] = mod

    cfg = ModulesConfig(
        modules=[
            ModuleSpec(
                name="battery",
                version=">=1.0.0",
                import_path="fake.battery:module",
                depends_on=[DependencySpec(name="rec", version=">=1.0.0")],
            )
        ]
    )

    with pytest.raises(ValueError, match="depends on missing"):
        load_and_register_modules(registry=DTRegistry(), cfg=cfg)
