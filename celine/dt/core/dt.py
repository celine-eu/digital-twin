from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, TYPE_CHECKING

from celine.dt.core.utils import utc_now

# avoid dependency loop
if TYPE_CHECKING:
    from celine.dt.core.registry import DTRegistry
    from celine.dt.core.runner import DTAppRunner
    from celine.dt.core.state import StateStore
    from celine.dt.core.auth.provider import TokenProvider
    from celine.dt.core.values.service import ValuesService
    from dt.core.context import RunContext

logger = logging.getLogger(__name__)


class DT:
    """Digital Twin runtime core.

    This object is transport-agnostic. API layers (FastAPI or others) should act as
    thin gates that delegate to this runtime.

    The DT instance is intended to be application-scoped.
    Request-scoped attributes (request_id, now, auth context, etc.) are carried by
    a per-invocation RunContext which is a lightweight shim inheriting from DT.
    """

    def __init__(
        self,
        *,
        registry: DTRegistry,
        runner: DTAppRunner,
        values: ValuesService,
        state: StateStore,
        token_provider: TokenProvider | None,
        services: Mapping[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner
        self.values = values
        self.state = state
        self.token_provider = token_provider
        self.services: Mapping[str, Any] = services or {}

    # ---------------------------------------------------------------------
    # Apps
    # ---------------------------------------------------------------------

    def list_apps(self) -> list[dict[str, str]]:
        return self.registry.list_apps()

    def describe_app(self, app_key: str) -> dict[str, Any]:
        return self.registry.describe_app(app_key)

    async def run_app(
        self,
        *,
        app_key: str,
        payload: Mapping[str, Any] | None,
        context: Any,
    ) -> Any:
        """Execute a registered app."""
        return await self.runner.run(
            registry=self.registry,
            app_key=app_key,
            payload=payload,
            context=context,
        )

    # ---------------------------------------------------------------------
    # Context
    # ---------------------------------------------------------------------

    def create_context(
        self,
        *,
        request: Any | None = None,
        request_scope: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> "RunContext":
        from celine.dt.core.context import RunContext  # local import to avoid cycles

        return RunContext.from_dt(
            self,
            request=request,
            request_scope=request_scope,
            request_id=request_id,
            now=now or utc_now(),
        )
