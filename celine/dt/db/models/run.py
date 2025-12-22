from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from celine.dt.db.base import Base


class Run(Base):
    __tablename__ = "run"

    run_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="created"
    )  # created|running|success|failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class RunResult(Base):
    __tablename__ = "run_result"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    results_jsonld: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
