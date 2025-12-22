from __future__ import annotations
from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.db.session import get_async_sessionmaker
from celine.dt.core.registry import AppRegistry


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = get_async_sessionmaker()
    async with SessionLocal() as session:
        yield session


def get_registry(request: Request) -> AppRegistry:
    return request.app.state.registry


def get_jsonld_context_files(request: Request) -> list[str]:
    return request.app.state.jsonld_context_files
