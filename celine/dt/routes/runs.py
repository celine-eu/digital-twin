from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.routes.deps import get_session, get_registry, get_jsonld_context_files
from celine.dt.api.schemas import RunCreateRequest, RunCreateResponse, RunResultResponse
from celine.dt.api.runs import create_run, get_run_results
from celine.dt.api.exceptions import NotFound, BadRequest

def map_domain_error(e: Exception):
    if isinstance(e, NotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, BadRequest):
        raise HTTPException(status_code=400, detail=str(e))


logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-runs"])

@router.post("/scenarios/{scenario_id}/runs", response_model=RunCreateResponse)
async def create_run_route(
    scenario_id: str,
    req: RunCreateRequest,
    session: AsyncSession = Depends(get_session),
    registry = Depends(get_registry),
    jsonld_context_files: list[str] = Depends(get_jsonld_context_files),
) -> RunCreateResponse:
    try:
        return await create_run(
            session=session,
            registry=registry,
            jsonld_context_files=jsonld_context_files,
            scenario_id=scenario_id,
            req=req,
        )
    except HTTPException:
        raise
    except Exception as e:
        try:
            map_domain_error(e)
        except HTTPException:
            raise
        logger.exception("Run failed", extra={"scenario_id": scenario_id})
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/runs/{run_id}/results", response_model=RunResultResponse)
async def get_run_results_route(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunResultResponse:
    try:
        return await get_run_results(session=session, run_id=run_id)
    except HTTPException:
        raise
    except Exception as e:
        try:
            map_domain_error(e)
        except HTTPException:
            raise
        raise HTTPException(status_code=500, detail=str(e))
