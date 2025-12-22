from __future__ import annotations

import functools
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from celine.dt.core.config import settings

@functools.lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    # Expect an async SQLAlchemy URL, e.g. postgresql+asyncpg://...
    return create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
