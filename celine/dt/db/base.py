from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from celine.dt.core.config import settings


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""

    metadata = MetaData(schema=settings.database_schema)
