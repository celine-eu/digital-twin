# tests/api/test_values.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from celine.dt.api.values import router as values_router
from celine.dt.core.values.registry import ValuesRegistry, FetcherDescriptor
from celine.dt.core.values.config import ValueFetcherSpec
from celine.dt.core.values.executor import ValuesFetcher


class FakeDatasetClient:
    """Fake client for testing."""

    def __init__(self, return_value=None):
        self.return_value = return_value or []
        self.last_query = None

    async def query(self, *, sql: str, limit: int = 100, offset: int = 0):
        self.last_query = sql
        return self.return_value


def create_test_app(values_registry: ValuesRegistry) -> FastAPI:
    """Create a FastAPI app with values router for testing."""
    app = FastAPI()
    app.state.values_registry = values_registry
    app.state.values_fetcher = ValuesFetcher()
    app.include_router(values_router, prefix="/values")
    return app


class TestListValues:
    def test_list_empty(self):
        registry = ValuesRegistry()
        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_fetchers(self):
        registry = ValuesRegistry()
        fake_client = FakeDatasetClient()

        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(id="fetcher_a", client="c"),
                client=fake_client,
            )
        )
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="fetcher_b",
                    client="c",
                    payload_schema={"type": "object"},
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        ids = {f["id"] for f in data}
        assert ids == {"fetcher_a", "fetcher_b"}


class TestDescribeValue:
    def test_describe_existing(self):
        registry = ValuesRegistry()
        fake_client = FakeDatasetClient()

        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="my_fetcher",
                    client="dataset_api",
                    query="SELECT * FROM t",
                    limit=50,
                    payload_schema={
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    },
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/my_fetcher/describe")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "my_fetcher"
        assert data["client"] == "dataset_api"
        assert data["limit"] == 50
        assert data["payload_schema"] is not None

    def test_describe_not_found(self):
        registry = ValuesRegistry()
        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/nonexistent/describe")

        assert resp.status_code == 404


class TestGetValue:
    def test_get_simple(self):
        fake_client = FakeDatasetClient(return_value=[{"id": 1}, {"id": 2}])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT * FROM t",
                    limit=100,
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == [{"id": 1}, {"id": 2}]
        assert data["count"] == 2

    def test_get_with_params(self):
        fake_client = FakeDatasetClient(return_value=[])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT * FROM t WHERE id = :id",
                    payload_schema={
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    },
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/test?id=42")

        assert resp.status_code == 200
        assert fake_client.last_query and "WHERE id = 42" in fake_client.last_query

    def test_get_with_limit_offset(self):
        fake_client = FakeDatasetClient(return_value=[])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(id="test", client="c", query="SELECT 1"),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/test?limit=10&offset=5")

        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_get_coerces_types(self):
        fake_client = FakeDatasetClient(return_value=[])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT * FROM t WHERE count > :count",
                    payload_schema={
                        "type": "object",
                        "properties": {"count": {"type": "number"}},
                    },
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/test?count=3.14")

        assert resp.status_code == 200
        # Number should be coerced and formatted
        assert fake_client.last_query and "3.14" in fake_client.last_query

    def test_get_missing_required_param(self):
        fake_client = FakeDatasetClient()
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT 1",
                    payload_schema={
                        "type": "object",
                        "required": ["must_have"],
                        "properties": {"must_have": {"type": "string"}},
                    },
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/test")

        assert resp.status_code == 400

    def test_get_not_found(self):
        registry = ValuesRegistry()
        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.get("/values/nonexistent")

        assert resp.status_code == 404


class TestPostValue:
    def test_post_simple(self):
        fake_client = FakeDatasetClient(return_value=[{"id": 1}])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT * FROM t WHERE id = :id",
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.post("/values/test", json={"id": 42})

        assert resp.status_code == 200
        assert fake_client.last_query and "WHERE id = 42" in fake_client.last_query

    def test_post_with_validation(self):
        fake_client = FakeDatasetClient(return_value=[])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(
                    id="test",
                    client="c",
                    query="SELECT 1",
                    payload_schema={
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                ),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        # Valid payload
        resp = client.post("/values/test", json={"name": "test", "count": 5})
        assert resp.status_code == 200

        # Invalid payload (wrong type)
        resp = client.post("/values/test", json={"name": "test", "count": "not_int"})
        assert resp.status_code == 400

        # Invalid payload (missing required)
        resp = client.post("/values/test", json={"count": 5})
        assert resp.status_code == 400

    def test_post_with_limit_offset(self):
        fake_client = FakeDatasetClient(return_value=[])
        registry = ValuesRegistry()
        registry.register(
            FetcherDescriptor(
                spec=ValueFetcherSpec(id="test", client="c", query="SELECT 1"),
                client=fake_client,
            )
        )

        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.post("/values/test?limit=10&offset=5", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_post_not_found(self):
        registry = ValuesRegistry()
        app = create_test_app(registry)
        client = TestClient(app)

        resp = client.post("/values/nonexistent", json={})

        assert resp.status_code == 404
