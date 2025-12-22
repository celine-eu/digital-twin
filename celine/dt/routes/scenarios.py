from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.routes.deps import get_session, get_registry
from celine.dt.api.schemas import ScenarioCreateRequest, ScenarioCreateResponse
from celine.dt.api.scenarios import create_scenario
from celine.dt.api.exceptions import NotFound, BadRequest

def map_domain_error(e: Exception):
    if isinstance(e, NotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, BadRequest):
        raise HTTPException(status_code=400, detail=str(e))


logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-scenarios"])

@router.post("/recs/{rec_id}/scenarios", response_model=ScenarioCreateResponse)
async def create_scenario_route(
    rec_id: str,
    req: ScenarioCreateRequest,
    session: AsyncSession = Depends(get_session),
    registry = Depends(get_registry),
) -> ScenarioCreateResponse:
    try:
        return await create_scenario(session=session, registry=registry, rec_id=rec_id, req=req)
    except HTTPException:
        raise
    except Exception as e:
        try:
            map_domain_error(e)
        except HTTPException:
            raise
        logger.exception("Scenario creation failed", extra={"rec_id": rec_id, "app_key": req.app_key})
        raise HTTPException(status_code=500, detail=str(e))
