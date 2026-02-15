# celine/dt/api/context.py
"""
Domain context via FastAPI dependency injection.

No factories, no wrappers. Just Depends(get_context).
Domain is resolved from the request path prefix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
import uuid
from celine.sdk.auth import JwtUser
from fastapi import Depends, HTTPException, Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.broker.service import BrokerService
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.values.service import ValuesService
from celine.dt.core.domain.registry import DomainRegistry

DomainT = TypeVar("DomainT", bound=DTDomain)
EntityT = TypeVar("EntityT", bound=EntityInfo)


@dataclass
class Ctx(Generic[DomainT, EntityT]):
    """Request context for domain route handlers."""

    entity: EntityT
    domain: DomainT
    values_service: ValuesService
    broker_service: BrokerService
    request: Request

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    user: JwtUser | None = None
    token: str | None = None

    async def fetch_value(
        self, fetcher_id: str, payload: dict | None = None, **kw
    ) -> Any:
        if not self.values_service:
            raise RuntimeError("values_service not available")
        return await self.values_service.fetch(
            fetcher_id=f"{self.domain.name}.{fetcher_id}",
            payload=payload or {},
            entity=self.entity,
            **kw,
        )

    async def publish(self, topic: str, payload: Any, **kw) -> Any:
        if not self.broker_service:
            return None
        return await self.broker_service.publish_event(
            topic=topic, payload=payload, **kw
        )


def _parse_jwt(request: Request):
    auth = request.headers.get("authorization")
    if not auth:
        return None
    try:
        return JwtUser.from_token(auth, verify=False)
    except:
        return None


def _find_domain(request: Request) -> DTDomain | None:
    """Find domain by matching route prefix to registered domains."""
    domain_registry: DomainRegistry = request.app.state.domain_registry
    path = request.url.path

    return domain_registry.match_path(path)


async def get_ctx(request: Request) -> Ctx[DTDomain, EntityInfo]:
    """
    Main context dependency. Use as: Depends(get_ctx)

    Resolves domain from URL prefix, entity from path param.
    """
    domain = _find_domain(request)
    if not domain:
        print(getattr(request.app.state, "domains", {}))
        raise HTTPException(500, f"No domain matches this route: {request.url.path}")

    entity_id = request.path_params.get(domain.entity_id_param)
    if not entity_id:
        raise HTTPException(400, f"Missing path param: {domain.entity_id_param}")

    entity = await domain.resolve_entity(entity_id, request)
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    token = request.headers.get("authorization", None) if request else None
    if token and token.strip().lower().startswith("bearer "):
        parts = token.strip().split()
        token = parts[-1] if parts else token

    return Ctx(
        entity=entity,
        domain=domain,
        values_service=request.app.state.values_service,
        broker_service=request.app.state.broker_service,
        request=request,
        user=_parse_jwt(request),
        token=token,
    )


async def get_ctx_auth(
    ctx: Ctx[DTDomain, EntityInfo] = Depends(get_ctx),
) -> Ctx[DTDomain, EntityInfo]:
    """Context with required authentication."""
    if not ctx.user:
        raise HTTPException(401, "Authentication required")
    return ctx
