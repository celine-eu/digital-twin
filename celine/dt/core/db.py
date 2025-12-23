# celine/dt/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from celine.dt.core.config import settings

# Naming convention is strongly recommended for Alembic compatibility
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        logger.info("Creating async DB engine")
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """
    Async context manager for DB sessions.
    Use ONLY in core / API layers, not inside apps.
    """
    Session = get_sessionmaker()
    async with Session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("DB transaction rolled back")
            raise


class Base(DeclarativeBase):
    """
    Shared SQLAlchemy Declarative Base for the DT runtime.

    - Uses a single metadata instance
    - All tables are created in `settings.database_schema`
    - Safe for Alembic migrations
    """

    metadata = MetaData(
        schema=settings.database_schema,
        naming_convention=NAMING_CONVENTION,
    )
