# celine/dt/api/discovery.py
"""
Root-level discovery and health endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    broker = getattr(request.app.state, "broker_service", None)
    domains = getattr(request.app.state, "domain_registry", None)
    return {
        "status": "healthy",
        "broker": "connected" if broker and broker.has_brokers() else "not configured",
        "domains": len(domains) if domains else 0,
    }


@router.get("/domains")
async def list_domains(request: Request) -> list[dict]:
    """Discover all registered domains and their capabilities."""
    registry = getattr(request.app.state, "domain_registry", None)
    if registry is None:
        return []
    return registry.list()
