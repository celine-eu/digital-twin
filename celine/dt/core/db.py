from __future__ import annotations

from sqlmodel import SQLModel, create_engine, Session
from celine.dt.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)


def init_db() -> None:
    # For PoC: create tables. In production use Alembic.
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
