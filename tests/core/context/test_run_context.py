from celine.dt.core.context import RunContext
from celine.dt.core.dt import DT
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.state import MemoryStateStore
from celine.dt.core.values.executor import ValuesFetcher
from celine.dt.core.values.registry import ValuesRegistry
from celine.dt.core.values.service import ValuesService


def test_run_context_exposes_dt_services():
    dt = DT(
        registry=DTRegistry(),
        runner=DTAppRunner(),
        values=ValuesService(registry=ValuesRegistry(), fetcher=ValuesFetcher()),
        state=MemoryStateStore(),
        token_provider=None,
        services={},
    )

    ctx = dt.create_context(request=None, request_scope={"tenant": "demo"})

    assert isinstance(ctx, RunContext)
    assert ctx.values is dt.values
    assert ctx.state is dt.state
    assert ctx.token_provider is None
    assert ctx.request_id
    assert ctx.request_scope["tenant"] == "demo"
