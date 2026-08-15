# celine/dt/api/discovery.py
"""
Root-level discovery and health endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from celine.dt.core.domain.registry import DomainRegistry

router = APIRouter()


def _domain_registry(request: Request) -> DomainRegistry | None:
    """Read the registry off `app.state.infra`.

    `create_app` sets `app.state.infra` and nothing else, so reading a bare
    `app.state.domain_registry` here yields None on a fully loaded service — an
    empty `/domains` and a health check reporting zero domains, both with a 200.
    `Infrastructure.domain_registry` raises until domain loading completes, which
    is a legitimate state during startup, so it is caught rather than propagated.
    """
    infra = getattr(request.app.state, "infra", None)
    if infra is None:
        return None
    try:
        return infra.domain_registry
    except RuntimeError:
        return None


@router.get("/health")
async def health(request: Request) -> dict:
    infra = getattr(request.app.state, "infra", None)
    broker = getattr(infra, "broker", None)
    domains = _domain_registry(request)
    return {
        "status": "healthy",
        "broker": "connected" if broker and broker.has_brokers() else "not configured",
        "domains": len(domains) if domains else 0,
    }


@router.get("/domains")
async def list_domains(request: Request) -> list[dict]:
    """Discover all registered domains and their capabilities."""
    registry = _domain_registry(request)
    if registry is None:
        return []
    return registry.list()
