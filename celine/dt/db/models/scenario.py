from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from celine.dt.db.base import Base


class Scenario(Base):
    __tablename__ = "scenario"

    scenario_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    rec_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    app_key: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload_jsonld: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
