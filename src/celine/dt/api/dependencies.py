# celine/dt/api/dependencies.py
"""
FastAPI dependencies for request-scoped services.

Provides:
- ``get_jwt_user``: Extract ``JwtUser`` from ``Authorization`` header.
- ``get_optional_jwt_user``: Same but returns ``None`` if no header.
- ``get_run_context``: Build a ``RunContext`` for the current request.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from celine.sdk.auth import JwtUser

from celine.dt.core.auth import parse_jwt_user
from celine.dt.core.context import RunContext
from celine.dt.contracts.entity import EntityInfo

logger = logging.getLogger(__name__)


async def get_optional_jwt_user(
    authorization: str | None = Header(default=None),
) -> JwtUser | None:
    """Extract JWT user from Authorization header, or None if absent."""
    if not authorization:
        return None
    try:
        return parse_jwt_user(authorization)
    except ValueError as exc:
        logger.warning("Invalid JWT token: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


async def get_jwt_user(
    user: JwtUser | None = Depends(get_optional_jwt_user),
) -> JwtUser:
    """Require a valid JWT user — returns 401 if missing or invalid."""
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required",
        )
    if user.is_expired():
        raise HTTPException(status_code=401, detail="Token expired")
    return user


def make_run_context(
    request: Request,
    entity: EntityInfo | None = None,
) -> RunContext:
    """Build a RunContext from the current request and app state."""
    values_svc = getattr(request.app.state, "values_service", None)
    broker_svc = getattr(request.app.state, "broker_service", None)
    clients_reg = getattr(request.app.state, "clients_registry", None)

    services: dict[str, Any] = {}
    if clients_reg:
        services["clients_registry"] = clients_reg

    return RunContext(
        entity=entity,
        values_service=values_svc,
        broker_service=broker_svc,
        services=services,
    )
