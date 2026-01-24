from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from celine.dt.core.dt import DT
from celine.dt.core.values.executor import ValuesFetcher
from celine.dt.core.values.registry import ValuesRegistry
from celine.dt.core.values.service import ValuesService
from celine.dt.contracts.state import AppState
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import StateStore


@dataclass
class _NoopRunner(DTAppRunner):
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Runner is not used in values API tests")


@dataclass
class _NoopState(StateStore):
    async def get(self, app: str) -> AppState | None: ...
    async def set(self, state: AppState) -> None: ...
    async def update(self, app: str, **patch) -> AppState: ...


def ensure_dt_runtime(app: Any) -> None:
    """
    Ensure app.state.dt exists for API tests.

    Values API tests historically wired app.state.values_registry/values_fetcher directly.
    With DT-first architecture, routers expect app.state.dt to exist. This helper builds a
    minimal DT runtime that supports values endpoints (dt.values) and leaves other
    services as no-ops.

    This function is intentionally idempotent.
    """
    if getattr(app.state, "dt", None) is not None:
        return

    registry: Any = getattr(app.state, "values_registry", None)
    if registry is None:
        registry = ValuesRegistry()
        app.state.values_registry = registry

    fetcher = getattr(app.state, "values_fetcher", None)
    if fetcher is None:
        fetcher = ValuesFetcher()
        app.state.values_fetcher = fetcher

    values_service = ValuesService(registry=registry, fetcher=fetcher)

    app.state.dt = DT(
        registry=registry,  # noqa not required for values endpoint tests
        runner=_NoopRunner(),  # not required for values endpoint tests
        values=values_service,  # required
        state=_NoopState(),  # not required for values endpoint tests
        token_provider=None,  # not required for values endpoint tests
        services={},
    )
