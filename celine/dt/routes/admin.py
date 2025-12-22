from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.routes.deps import get_session
from celine.dt.api.admin import run_retention
from celine.dt.api.exceptions import NotFound, BadRequest

def map_domain_error(e: Exception):
    if isinstance(e, NotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, BadRequest):
        raise HTTPException(status_code=400, detail=str(e))


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/retention/run")
async def run_retention_route(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await run_retention(session=session)
    except HTTPException:
        raise
    except Exception as e:
        try:
            map_domain_error(e)
        except HTTPException:
            raise
        logger.exception("Retention job failed")
        raise HTTPException(status_code=500, detail=str(e))
