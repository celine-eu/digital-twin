from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from celine.dt.db.base import Base


class MaterializedTimeSeries(Base):
    __tablename__ = "materialized_timeseries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rec_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    load_kw: Mapped[float] = mapped_column(Float, nullable=False)
    pv_kw: Mapped[float] = mapped_column(Float, nullable=False)

    import_price_eur_per_kwh: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    export_price_eur_per_kwh: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )

    quality_flag: Mapped[str] = mapped_column(String, nullable=False, default="ok")
