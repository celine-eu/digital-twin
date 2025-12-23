from __future__ import annotations

import pytest
from sqlalchemy import text

from celine.dt.core.db import get_engine, session_scope


@pytest.mark.asyncio
async def test_session_scope_commit() -> None:
    async with session_scope() as session:
        await session.execute(text("SELECT 1"))


@pytest.mark.asyncio
async def test_session_scope_rollback() -> None:
    with pytest.raises(RuntimeError):
        async with session_scope():
            raise RuntimeError("boom")
