from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from celine.dt.core.db import Base
from celine.dt.core.config import settings


class ExampleModel(Base):
    __tablename__ = "example_table"

    id: Mapped[int] = mapped_column(primary_key=True)


def test_metadata_schema_applied() -> None:
    assert Base.metadata.schema == settings.database_schema

    key = f"{settings.database_schema}.example_table"
    assert key in Base.metadata.tables

    table = Base.metadata.tables[key]
    assert table.schema == settings.database_schema
