from celine.dt.core.runner import resolve_config

from celine.dt.core.runner import resolve_config
from pydantic import BaseModel


class DummyConfig(BaseModel):
    a: int
    b: int = 2


class DummyApp:
    config_type = DummyConfig
    input_mapper = None


def test_resolve_config_merges_defaults_and_payload():
    app = DummyApp()

    defaults = {"b": 10}
    payload = {"a": 5}

    cfg = resolve_config(
        app=app,
        defaults=defaults,
        payload=payload,
    )

    assert cfg.a == 5
    assert cfg.b == 10
