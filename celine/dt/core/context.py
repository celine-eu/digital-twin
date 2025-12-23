from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
import uuid

from celine.dt.core.auth.provider import TokenProvider
from celine.dt.core.datasets.client import DatasetClient
from celine.dt.core.state import StateStore
from celine.dt.core.utils import utc_now


@dataclass(frozen=True)
class RunContext:
    request_id: str
    now: datetime
    datasets: DatasetClient
    state: StateStore
    token_provider: TokenProvider
    services: Mapping[str, Any]
    request: Any | None = None

    @classmethod
    def create(
        cls,
        *,
        services: Mapping[str, Any] | None = None,
        request: Any | None = None,
        datasets: DatasetClient,
        token_provider: TokenProvider,
        state: StateStore,
    ) -> "RunContext":
        return cls(
            request_id=str(uuid.uuid4()),
            now=utc_now(),
            datasets=datasets,
            state=state,
            services=services or {},
            request=request,
            token_provider=token_provider,
        )
