from __future__ import annotations

from typing import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.core.db import session_scope


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in session_scope():
        yield session
