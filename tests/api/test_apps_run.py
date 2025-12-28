from fastapi.testclient import TestClient
from pydantic import BaseModel

from celine.dt.main import create_app


class DummyConfig(BaseModel):
    value: int


class DummyResult(BaseModel):
    doubled: int


class DummyApp:
    key = "dummy-app"
    version = "1.0.0"

    config_type = DummyConfig
    result_type = DummyResult

    input_mapper = None
    output_mapper = None

    async def run(self, config, context):
        return DummyResult(doubled=config.value * 2)


def test_run_dummy_app():
    app = create_app()

    # 🔑 explicitly inject the dummy app
    app.state.registry.register_app(DummyApp())

    client = TestClient(app)

    resp = client.post(
        "/apps/dummy-app/run",
        json={"value": 21},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["doubled"] == 42
