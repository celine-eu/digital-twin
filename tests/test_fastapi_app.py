# tests/integration/test_fastapi_app.py
from fastapi.testclient import TestClient
from celine.dt.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
