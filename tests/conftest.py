# tests/conftest.py
"""
Shared test scaffolding.

Everything here exists so a test can exercise the real runtime wiring without an
external service. Two things are faked and nothing else:

* the dataset client (``MockDatasetClient``) — the only outbound dependency the
  values path has;
* the JWT check — see ``build_app(authenticated=...)``.

Domain registration, route mounting, entity resolution, template rendering and the
values registry are all the production code paths.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import FastAPI
from starlette.requests import Request

from celine.dt.api.context import get_ctx, get_ctx_auth
from celine.dt.api.discovery import router as discovery_router
from celine.dt.api.domain_router import build_router
from celine.dt.contracts.infrastructure import Infrastructure
from celine.dt.core.broker.service import BrokerService
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry
from celine.dt.core.ontology.service import OntologyService
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.core.values.executor import FetcherDescriptor, ValuesFetcher
from celine.dt.core.values.service import ValuesRegistry, ValuesService


class MockDatasetClient:
    """In-memory stand-in for ``DatasetSqlApiClient``.

    The signature must track the real client's: the executor calls it with
    ``sql``/``limit``/``offset``/``ctx`` as keyword arguments, and a double that
    drops one fails with a TypeError that reads like a test bug rather than the
    signature drift it actually is.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.last_sql: str | None = None
        self.last_limit: int | None = None
        self.last_offset: int | None = None
        self.calls: int = 0

    async def query(
        self,
        *,
        sql: str,
        limit: int = 100,
        offset: int = 0,
        ctx: Any = None,
    ) -> list[dict[str, Any]]:
        self.last_sql = sql
        self.last_limit = limit
        self.last_offset = offset
        self.calls += 1
        return self.rows[offset : offset + limit]


def make_request(path: str = "/", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """A minimal Starlette ``Request``.

    ``DTDomain.resolve_entity`` takes a request so that overrides can read headers
    and app state. The default implementation ignores it, but the parameter is
    required, so tests of the default still need one.
    """
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers or [],
        }
    )


def make_infrastructure() -> Infrastructure:
    """An ``Infrastructure`` wired exactly as ``create_app`` wires it, minus I/O."""
    values_registry = ValuesRegistry()
    values_service = ValuesService(registry=values_registry, fetcher=ValuesFetcher())
    return Infrastructure(
        broker=BrokerService(),
        values_service=values_service,
        values_registry=values_registry,
        clients_registry=ClientsRegistry(),
        simulation_registry=SimulationRegistry(),
        ontology_service=OntologyService(values_service=values_service),
    )


def build_app(
    *domains: DTDomain,
    client: MockDatasetClient | None = None,
    authenticated: bool = True,
) -> FastAPI:
    """Wire a FastAPI app around one or more domains.

    Mirrors ``celine.dt.main.create_app``: the same ``build_router`` call, the same
    ``app.state.infra``, the same ``{domain.name}.{spec.id}`` namespacing applied to
    value specs. Value registration happens here rather than in a lifespan because
    the lifespan's other steps need OIDC and a broker.

    Args:
        authenticated: when True, ``get_ctx_auth`` is overridden with ``get_ctx``,
            so routes run with entity resolution intact but without a JWT. Pass
            False to exercise the 401 path itself.
    """
    infra = make_infrastructure()
    domain_registry = DomainRegistry()

    for domain in domains:
        domain.set_infrastructure(infra)
        domain_registry.register(domain)
        for spec in domain.get_value_specs():
            infra.values_registry.register(
                FetcherDescriptor(
                    spec=replace(spec, id=f"{domain.name}.{spec.id}"),
                    client=client or MockDatasetClient(),
                )
            )

    infra._domain_registry = domain_registry

    app = FastAPI()
    app.state.infra = infra
    app.include_router(discovery_router)
    for domain in domains:
        app.include_router(build_router(domain))

    if authenticated:
        # Drop only the JWT requirement. get_ctx still resolves the domain from the
        # path and the entity via the domain's own resolve_entity.
        app.dependency_overrides[get_ctx_auth] = get_ctx

    return app
