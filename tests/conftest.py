import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from celine.dt.db.base import Base
from celine.dt.core.config import settings
from celine.dt.adapters import registry as adapter_registry

TEST_DB_URL = settings.database_url.replace("postgresql+psycopg", "postgresql+asyncpg")


@pytest.fixture(autouse=True)
def reset_adapter_registry():
    adapter_registry._ADAPTER_MODULES.clear()
    yield
    adapter_registry._ADAPTER_MODULES.clear()


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    Session = async_sessionmaker(async_engine, expire_on_commit=False)
    async with Session() as session:
        yield session
