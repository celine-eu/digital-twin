from __future__ import annotations

import functools
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from celine.dt.db.engine import get_async_engine


@functools.lru_cache(maxsize=1)
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = get_async_engine()
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
