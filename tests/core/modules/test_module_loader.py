from __future__ import annotations

import types
import sys

from celine.dt.core.registry import DTRegistry
from celine.dt.core.modules.config import ModulesConfig, ModuleSpec
from celine.dt.core.modules.loader import load_and_register_modules


class DummyModule:
    name = "dummy"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(DummyApp())


class DummyApp:
    key = "dummy-app"
    version = "1.0.0"

    async def run(self, *_):
        return {}


def test_module_load_and_register(monkeypatch) -> None:
    # inject fake module path
    mod = types.ModuleType("fake.module")
    mod.module = DummyModule()
    sys.modules["fake.module"] = mod

    cfg = ModulesConfig(
        modules=[
            ModuleSpec(
                name="dummy",
                version=">=1.0.0",
                import_path="fake.module:module",
            )
        ]
    )

    registry = DTRegistry()
    load_and_register_modules(registry=registry, cfg=cfg)

    assert "dummy" in registry.modules
    assert "dummy-app" in registry.apps
