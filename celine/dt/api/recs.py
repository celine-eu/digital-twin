from __future__ import annotations

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session

from celine.dt.adapters.factory import get_dataset_adapter_for_app
from celine.dt.core.db import get_session
from celine.dt.core.config import settings
from celine.dt.simulation.kpis import compute_baseline_kpis
from celine.dt.api.schemas import MaterializeResponse, KPIResponse

from sqlmodel import select
import pandas as pd
from celine.dt.api.schemas import KPIResponse
from celine.dt.simulation.models import MaterializedTimeSeries

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-recs"])


@router.get("/recs/{rec_id}/kpis", response_model=KPIResponse)
async def rec_kpis(
    rec_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: Session = Depends(get_session),
) -> KPIResponse:
    try:
        rows = session.exec(
            select(MaterializedTimeSeries)
            .where(MaterializedTimeSeries.rec_id == rec_id)
            .where(MaterializedTimeSeries.ts >= start)
            .where(MaterializedTimeSeries.ts <= end)
            .order_by(MaterializedTimeSeries.ts)  # type: ignore
        ).all()
        if not rows:
            raise HTTPException(
                status_code=404, detail="No materialized timeseries for given range"
            )

        # Convert to DataFrame for KPI computation
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("KPI computation failed", extra={"rec_id": rec_id})
        raise HTTPException(status_code=500, detail=str(e))
