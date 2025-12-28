from __future__ import annotations

from celine.dt.core.registry import DTRegistry

from celine.dt.core.registry import DTRegistry


class DummyApp:
    key = "dummy"
    version = "1.0.0"

    class config_type:
        @staticmethod
        def model_json_schema():
            return {"type": "object"}

    class result_type:
        @staticmethod
        def model_json_schema():
            return {"type": "object"}


def test_describe_app_is_cached():
    registry = DTRegistry()
    registry.register_app(DummyApp())

    registry.describe_app("dummy")
    info1 = registry._describe_app_cached.cache_info()

    registry.describe_app("dummy")
    info2 = registry._describe_app_cached.cache_info()

    assert info2.hits == info1.hits + 1
