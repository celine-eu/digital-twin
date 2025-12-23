from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
import uuid

from celine.dt.core.utils import utc_now


@dataclass(frozen=True)
class RunContext:
    request_id: str
    now: datetime
    services: Mapping[str, Any]
    request: Any | None = None

    @classmethod
    def create(
        cls,
        *,
        services: Mapping[str, Any] | None = None,
        request: Any | None = None,
    ) -> "RunContext":
        return cls(
            request_id=str(uuid.uuid4()),
            now=utc_now(),
            services=services or {},
            request=request,
        )
