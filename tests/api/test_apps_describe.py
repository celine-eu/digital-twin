from fastapi.testclient import TestClient
from pydantic import BaseModel

from celine.dt.main import create_app


class DummyConfig(BaseModel):
    x: int


class DummyResult(BaseModel):
    y: int


class DummyApp:
    key = "dummy-app"
    version = "1.0.0"

    config_type = DummyConfig
    result_type = DummyResult

    input_mapper = None
    output_mapper = None

    async def run(self, config, context):
        return DummyResult(y=config.x)


def test_list_apps():
    app = create_app()
    app.state.registry.register_app(DummyApp())

    client = TestClient(app)

    resp = client.get("/apps")
    assert resp.status_code == 200

    apps = resp.json()
    assert any(a["key"] == "dummy-app" for a in apps)


def test_describe_app():
    app = create_app()
    app.state.registry.register_app(DummyApp())

    client = TestClient(app)

    resp = client.get("/apps/dummy-app/describe")
    assert resp.status_code == 200

    data = resp.json()
    assert data["key"] == "dummy-app"
    assert "input_schema" in data
    assert "output_schema" in data
