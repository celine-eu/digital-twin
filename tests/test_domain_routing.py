# tests/test_domain_routing.py
"""
Integration tests for domain-driven routing.

Uses FastAPI TestClient to verify end-to-end domain registration,
entity resolution, and route mounting.
"""
from __future__ import annotations

import pytest
from typing import Any, ClassVar

from fastapi.testclient import TestClient

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry
from celine.dt.core.values.executor import FetcherDescriptor, ValuesFetcher
from celine.dt.core.values.service import ValuesRegistry, ValuesService
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.api.domain_router import build_domain_router
from celine.dt.api.discovery import router as discovery_router

from fastapi import APIRouter, FastAPI


# -- fixtures / helpers --------------------------------------------------


class _MockClient:
    """In-memory mock for DatasetSqlApiClient."""

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.last_query: str | None = None

    async def query(self, *, sql: str, limit: int = 100, offset: int = 0) -> list[dict]:
        self.last_query = sql
        return self.rows[offset: offset + limit]


class SampleCommunityDomain(DTDomain):
    name: ClassVar[str] = "test-community"
    domain_type: ClassVar[str] = "energy-community"
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str] = "/communities"
    entity_id_param: ClassVar[str] = "community_id"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [
            ValueFetcherSpec(
                id="consumption",
                client="mock",
                query="SELECT * FROM consumption WHERE community_id = '{{ entity.id }}'",
                limit=100,
            ),
        ]

    def routes(self) -> APIRouter:
        router = APIRouter()
        domain = self

        @router.get("/summary")
        async def summary(community_id: str) -> dict:
            entity = await domain.resolve_entity(community_id)
            return {"id": entity.id, "domain": domain.name}

        return router


class StrictResolveDomain(DTDomain):
    """Domain that rejects unknown entities."""

    name: ClassVar[str] = "strict-community"
    domain_type: ClassVar[str] = "energy-community"
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str] = "/strict"
    entity_id_param: ClassVar[str] = "community_id"

    KNOWN = {"abc-123", "xyz-456"}

    async def resolve_entity(self, entity_id: str) -> EntityInfo | None:
        if entity_id not in self.KNOWN:
            return None
        return EntityInfo(
            id=entity_id,
            domain_name=self.name,
            metadata={"region": "trentino"},
        )


def _build_app(
    domain: DTDomain,
    mock_client: _MockClient | None = None,
) -> FastAPI:
    """Wire a single-domain test application."""
    values_registry = ValuesRegistry()
    values_fetcher = ValuesFetcher()
    values_service = ValuesService(registry=values_registry, fetcher=values_fetcher)
    simulation_registry = SimulationRegistry()

    client = mock_client or _MockClient()

    # Register domain value fetchers
    for spec in domain.get_value_specs():
        from dataclasses import replace
        ns_spec = replace(spec, id=f"{domain.name}.{spec.id}")
        values_registry.register(FetcherDescriptor(spec=ns_spec, client=client))

    # Build app
    app = FastAPI()
    app.state.domain_registry = DomainRegistry()
    app.state.domain_registry.register(domain)
    app.state.values_service = values_service
    app.state.simulation_registry = simulation_registry

    router = build_domain_router(
        domain,
        values_service=values_service,
        simulation_registry=simulation_registry,
    )
    app.include_router(router, prefix=domain.route_prefix)
    app.include_router(discovery_router)

    return app


# -- tests ---------------------------------------------------------------


class TestDomainDiscovery:
    def test_health(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_domains_list(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/domains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-community"
        assert data[0]["domain_type"] == "energy-community"


class TestEntityRouting:
    def test_domain_info(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/communities/rec-folgaria")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "rec-folgaria"
        assert data["domain"] == "test-community"
        assert "consumption" in data["values"]

    def test_entity_resolution_reject(self):
        domain = StrictResolveDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/strict/unknown-id")
        assert resp.status_code == 404

    def test_entity_resolution_accept(self):
        domain = StrictResolveDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/strict/abc-123")
        assert resp.status_code == 200
        assert resp.json()["entity_id"] == "abc-123"


class TestValueRoutes:
    def test_list_values(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/communities/rec-1/values")
        assert resp.status_code == 200
        ids = [v["id"] for v in resp.json()]
        assert "consumption" in ids

    def test_fetch_value_get(self):
        mock = _MockClient(rows=[{"kwh": 42.0}])
        domain = SampleCommunityDomain()
        app = _build_app(domain, mock)
        client = TestClient(app)
        resp = client.get("/communities/rec-1/values/consumption")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["items"][0]["kwh"] == 42.0
        # Verify entity ID was injected into the query template
        assert "rec-1" in mock.last_query

    def test_fetch_value_post(self):
        mock = _MockClient(rows=[{"kwh": 10.0}])
        domain = SampleCommunityDomain()
        app = _build_app(domain, mock)
        client = TestClient(app)
        resp = client.post(
            "/communities/rec-1/values/consumption",
            json={"payload": {}},
        )
        assert resp.status_code == 200

    def test_fetch_value_not_found(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/communities/rec-1/values/nonexistent")
        assert resp.status_code == 404


class TestCustomRoutes:
    def test_custom_route(self):
        domain = SampleCommunityDomain()
        app = _build_app(domain)
        client = TestClient(app)
        resp = client.get("/communities/rec-1/summary")
        assert resp.status_code == 200
        assert resp.json()["id"] == "rec-1"
        assert resp.json()["domain"] == "test-community"
