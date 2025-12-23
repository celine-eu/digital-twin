from celine.dt.core.context import RunContext


def test_run_context_contains_core_services():
    ctx = RunContext.create(
        datasets="ds",
        state="state",
        token_provider="token",
    )

    assert ctx.datasets == "ds"
    assert ctx.state == "state"
    assert ctx.token_provider == "token"
    assert ctx.request_id
