from __future__ import annotations

import logging
from datetime import datetime
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.db.models import MaterializedTimeSeries
from celine.dt.simulation.kpis import compute_baseline_kpis
from celine.dt.api.schemas import KPIResponse
from celine.dt.api.exceptions import NotFound

logger = logging.getLogger(__name__)

async def compute_rec_kpis(
    *,
    session: AsyncSession,
    rec_id: str,
    start: datetime,
    end: datetime,
) -> KPIResponse:
    stmt = (
        select(MaterializedTimeSeries)
        .where(MaterializedTimeSeries.rec_id == rec_id)
        .where(MaterializedTimeSeries.ts >= start)
        .where(MaterializedTimeSeries.ts <= end)
        .order_by(MaterializedTimeSeries.ts)
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    if not rows:
        raise NotFound("No materialized timeseries for given range")

    df = pd.DataFrame(
        [
            {
                "ts": r.ts,
                "load_kw": r.load_kw,
                "pv_kw": r.pv_kw,
                "import_price_eur_per_kwh": r.import_price_eur_per_kwh,
                "export_price_eur_per_kwh": r.export_price_eur_per_kwh,
            }
            for r in rows
        ]
    )
    kpis = compute_baseline_kpis(df)
    return KPIResponse(rec_id=rec_id, start=start, end=end, kpis=kpis)
