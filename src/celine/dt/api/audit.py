# celine/dt/api/audit.py
"""
Access audit for the entity-scoped routes (REQ-1080 - REQ-1083).

One record per request on the ``celine.audit`` logger: who read which twin, entity
and value. The record is ``celine.sdk.audit.audit_route``'s, attached to the entity
scope. The gates that refuse a request - ``require_user``, entity resolution in
``get_ctx`` and a domain's own checks - name their reason code with ``note_reason``
before they raise; ``audit_route`` records that code as ``denied`` whatever the
status (a 404 hiding an entity too), so a refused request is recorded once, and
never also as ``error``.

Discovery (``/health``, ``/domains``) is not entity-scoped and is not recorded.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celine.sdk.audit import audit_route, note_reason
from fastapi import Request

__all__ = ["ACTION", "audit_entity_access", "note_reason"]

# Every entity-scoped route reads; none changes the twin.
ACTION = "twin.read"


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


def audit_entity_access(domain_name: str, entity_param: str) -> Callable[..., Any]:
    """A router-level dependency recording the outcome of an entity-scoped request.

    No ``user=``: the caller is ``request.state.user`` as it stands when the request
    ends, so the user ``require_user`` verifies - resolved later than this
    dependency - is the one recorded.
    """
    return audit_route(
        ACTION, resource=lambda request: _resource(request, entity_param, domain_name)
    )
