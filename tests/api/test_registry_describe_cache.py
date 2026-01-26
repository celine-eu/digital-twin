from __future__ import annotations

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


def test_describe_app_returns_consistent_result():
    """Test that describe_app returns consistent results."""
    registry = DTRegistry()
    registry.register_app(DummyApp())

    result1 = registry.describe_app("dummy")
    result2 = registry.describe_app("dummy")

    # Results should be identical
    assert result1 == result2
    assert result1["key"] == "dummy"
    assert result1["version"] == "1.0.0"
