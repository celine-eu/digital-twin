from __future__ import annotations

from fastapi.testclient import TestClient

from celine.dt.main import create_app


def test_app_starts() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code in (200, 404)
