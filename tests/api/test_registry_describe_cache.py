from __future__ import annotations

from celine.dt.core.registry import DTRegistry
from celine.dt.modules.battery_sizing.module import module


def test_describe_app_is_cached() -> None:
    registry = DTRegistry()
    module.register(registry)

    # first call populates cache
    registry.describe_app("battery-sizing")
    info1 = registry._describe_app_cached.cache_info()

    # second call should hit cache
    registry.describe_app("battery-sizing")
    info2 = registry._describe_app_cached.cache_info()

    assert info2.hits == info1.hits + 1
