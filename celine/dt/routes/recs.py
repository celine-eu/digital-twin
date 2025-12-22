from __future__ import annotations

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.routes.deps import get_session
from celine.dt.api.recs import compute_rec_kpis
from celine.dt.api.exceptions import NotFound, BadRequest

def map_domain_error(e: Exception):
    if isinstance(e, NotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, BadRequest):
        raise HTTPException(status_code=400, detail=str(e))


logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-recs"])

@router.get("/recs/{rec_id}/kpis", response_model=None)
async def rec_kpis(
    rec_id: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await compute_rec_kpis(session=session, rec_id=rec_id, start=start, end=end)
    except HTTPException:
        raise
    except Exception as e:
        try:
            map_domain_error(e)
        except HTTPException:
            raise
        logger.exception("KPI computation failed", extra={"rec_id": rec_id})
        raise HTTPException(status_code=500, detail=str(e))
