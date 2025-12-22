from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncEngine

from celine.dt.db.base import Base

logger = logging.getLogger(__name__)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables (PoC). In production prefer Alembic migrations."""
    # Import models to register them in metadata
    import celine.dt.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("DB initialized (create_all)")
