from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from celine.dt.core.dt import DT


@dataclass(frozen=True)
class RunContext(DT):
    """Per-invocation execution context.

    RunContext is a thin typing shim over the DT core, carrying request-scoped
    metadata while exposing the full DT capabilities to apps.

    The DT core remains application-scoped; RunContext is created for each
    invocation (API request, batch job run, etc.).
    """

    request_id: str
    now: datetime
    request_scope: Mapping[str, Any]
    request: Any | None = None

    @classmethod
    def from_dt(
        cls,
        dt: DT,
        *,
        request: Any | None = None,
        request_scope: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        now: datetime,
    ) -> "RunContext":
        # DT is not a dataclass; call its initializer explicitly.
        obj = cls.__new__(cls)

        DT.__init__(
            obj,
            registry=dt.registry,
            runner=dt.runner,
            values=dt.values,
            state=dt.state,
            token_provider=dt.token_provider,
            services=dt.services,
        )

        # Dataclass frozen, so set via object.__setattr__
        object.__setattr__(obj, "request_id", request_id or str(uuid.uuid4()))
        object.__setattr__(obj, "now", now)
        object.__setattr__(obj, "request_scope", request_scope or {})
        object.__setattr__(obj, "request", request)

        return obj
