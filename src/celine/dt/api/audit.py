# celine/dt/api/audit.py
"""
Access audit for the entity-scoped routes (REQ-1080 - REQ-1083).

One record per request on the ``celine.audit`` logger (``celine.sdk.audit``): who
read which twin, entity and value. The gates that refuse a request - ``require_user``
and entity resolution in ``get_ctx`` - note a short reason code on
``request.state``; the dependency here turns the outcome into the record, so a
refused request is recorded once, as ``denied``, and never also as ``error``.

Discovery (``/health``, ``/domains``) is not entity-scoped and is not recorded.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from celine.sdk.audit import audit_access, audit_denied
from fastapi import HTTPException, Request

# Every entity-scoped route reads; none changes the twin.
ACTION = "twin.read"

_REASON_ATTR = "audit_reason"
_DENIED_STATUSES = (401, 403)


def note_denial(request: Request, reason: str) -> None:
    """Record why a gate is about to refuse ``request``; read by ``audit_entity_access``."""
    setattr(request.state, _REASON_ATTR, reason)


def _resource(request: Request, entity_param: str, domain_name: str) -> str | None:
    """``{domain}/{entity}`` then any further path parameter (fetcher or spec id).

    Path parameters only: the query string carries meter ids and time ranges, which
    the route template already says are there.
    """
    params: dict[str, Any] = dict(request.path_params)
    entity_id = params.pop(entity_param, None)
    if entity_id is None:
        return None
    return "/".join([domain_name, str(entity_id), *(str(v) for v in params.values())])


def audit_entity_access(domain_name: str, entity_param: str):
    """A router-level dependency recording the outcome of an entity-scoped request.

    The caller is read from ``request.state.user`` *after* the route has run, so the
    user verified by ``require_user`` - resolved later than this dependency - is the
    one recorded.
    """

    async def dependency(request: Request) -> AsyncIterator[None]:
        try:
            yield
        except HTTPException as exc:
            reason = getattr(request.state, _REASON_ATTR, None)
            caller = getattr(request.state, "user", None)
            resource = _resource(request, entity_param, domain_name)
            if exc.status_code in _DENIED_STATUSES or reason:
                audit_denied(
                    ACTION,
                    caller=caller,
                    resource=resource,
                    reason=reason or f"http {exc.status_code}",
                    request=request,
                )
            else:
                audit_access(
                    ACTION,
                    caller=caller,
                    resource=resource,
                    outcome="error",
                    reason=f"http {exc.status_code}",
                    request=request,
                )
            raise
        except Exception as exc:
            audit_access(
                ACTION,
                caller=getattr(request.state, "user", None),
                resource=_resource(request, entity_param, domain_name),
                outcome="error",
                reason=type(exc).__name__,
                request=request,
            )
            raise
        else:
            audit_access(
                ACTION,
                caller=getattr(request.state, "user", None),
                resource=_resource(request, entity_param, domain_name),
                request=request,
            )

    return dependency
