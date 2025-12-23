import pytest

from celine.dt.core.state import MemoryStateStore
from celine.dt.contracts.state import AppStatus


@pytest.mark.asyncio
async def test_state_store_update_creates_and_updates():
    store = MemoryStateStore()

    state = await store.update("app1", status=AppStatus.RUNNING)
    assert state.status == AppStatus.RUNNING

    state2 = await store.update("app1", status=AppStatus.COMPLETED)
    assert state2.status == AppStatus.COMPLETED
