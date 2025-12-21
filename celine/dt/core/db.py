from __future__ import annotations

from sqlmodel import SQLModel, create_engine, Session
from celine.dt.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=(
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {}
    ),
    pool_pre_ping=True,
)


def init_db() -> None:
    # For PoC: create tables. In production use Alembic.
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
