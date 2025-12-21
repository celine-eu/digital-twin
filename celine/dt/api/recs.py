from __future__ import annotations

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session

from celine.dt.core.db import get_session
from celine.dt.core.config import settings
from celine.dt.main_deps import get_dataset_adapter
from celine.dt.simulation.materialize import upsert_timeseries, load_timeseries
from celine.dt.simulation.kpis import compute_baseline_kpis
from celine.dt.api.schemas import MaterializeResponse, KPIResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-recs"])


@router.post("/recs/{rec_id}/materialize", response_model=MaterializeResponse)
async def materialize_rec(
    rec_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    granularity: str = Query(default=settings.default_granularity),
    session: Session = Depends(get_session),
) -> MaterializeResponse:
    adapter = get_dataset_adapter()
    try:
        df = await adapter.fetch_timeseries(rec_id, start, end, granularity)
        rows = upsert_timeseries(session, rec_id, df)
        return MaterializeResponse(rec_id=rec_id, rows_inserted=rows)
    except Exception as e:
        logger.exception("Materialization failed", extra={"rec_id": rec_id})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recs/{rec_id}/kpis", response_model=KPIResponse)
def rec_kpis(
    rec_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: Session = Depends(get_session),
) -> KPIResponse:
    try:
        df = load_timeseries(session, rec_id, start, end)
        if df.empty:
            raise HTTPException(
                status_code=404,
                detail="No materialized timeseries found for given range",
            )
        kpis = compute_baseline_kpis(df)
        return KPIResponse(rec_id=rec_id, start=start, end=end, kpis=kpis)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("KPI computation failed", extra={"rec_id": rec_id})
        raise HTTPException(status_code=500, detail=str(e))
