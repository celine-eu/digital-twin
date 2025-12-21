from __future__ import annotations

import logging
from datetime import datetime
import pandas as pd
from sqlmodel import Session, select

from .models import MaterializedTimeSeries

logger = logging.getLogger(__name__)


def upsert_timeseries(session: Session, rec_id: str, df: pd.DataFrame) -> int:
    # For PoC: delete in range and insert. Replace with merge/upsert for production scale.
    if df.empty:
        return 0
    ts_min = df["ts"].min().to_pydatetime()
    ts_max = df["ts"].max().to_pydatetime()

    existing = session.exec(
        select(MaterializedTimeSeries).where(
            (MaterializedTimeSeries.rec_id == rec_id) &
            (MaterializedTimeSeries.ts >= ts_min) &
            (MaterializedTimeSeries.ts <= ts_max)
        )
    ).all()
    for row in existing:
        session.delete(row)
    session.commit()

    rows = []
    for r in df.to_dict(orient="records"):
        rows.append(
            MaterializedTimeSeries(
                rec_id=rec_id,
                ts=r["ts"].to_pydatetime() if hasattr(r["ts"], "to_pydatetime") else r["ts"],
                load_kw=float(r.get("load_kw", 0.0)),
                pv_kw=float(r.get("pv_kw", 0.0)),
                import_price_eur_per_kwh=float(r.get("import_price_eur_per_kwh", 0.0)),
                export_price_eur_per_kwh=float(r.get("export_price_eur_per_kwh", 0.0)),
                quality_flag=str(r.get("quality_flag", "ok")),
            )
        )
    session.add_all(rows)
    session.commit()
    return len(rows)


def load_timeseries(session: Session, rec_id: str, start: datetime, end: datetime) -> pd.DataFrame:
    rows = session.exec(
        select(MaterializedTimeSeries).where(
            (MaterializedTimeSeries.rec_id == rec_id) &
            (MaterializedTimeSeries.ts >= start) &
            (MaterializedTimeSeries.ts <= end)
        ).order_by(MaterializedTimeSeries.ts)
    ).all()
    df = pd.DataFrame([{
        "ts": r.ts,
        "load_kw": r.load_kw,
        "pv_kw": r.pv_kw,
        "import_price_eur_per_kwh": r.import_price_eur_per_kwh,
        "export_price_eur_per_kwh": r.export_price_eur_per_kwh,
    } for r in rows])
    return df
