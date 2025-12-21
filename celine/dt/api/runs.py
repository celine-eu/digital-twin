from __future__ import annotations

import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from celine.dt.core.db import get_session
from celine.dt.core.registry import AppRegistry
from celine.dt.core.jsonld import with_context
from celine.dt.simulation.materialize import load_timeseries
from celine.dt.simulation.models import Scenario, Run, RunResult
from celine.dt.api.schemas import RunCreateRequest, RunCreateResponse, RunResultResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-runs"])


@router.post("/scenarios/{scenario_id}/runs", response_model=RunCreateResponse)
def create_run(
    scenario_id: str,
    req: RunCreateRequest,
    session: Session = Depends(get_session),
    registry: AppRegistry = Depends(lambda: AppRegistryHolder.registry),
) -> RunCreateResponse:
    run_id = f"run-{uuid.uuid4().hex}"
    try:
        scenario = session.exec(
            select(Scenario).where(Scenario.scenario_id == scenario_id)
        ).one_or_none()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        app = registry.apps.get(scenario.app_key)
        if not app:
            raise HTTPException(
                status_code=404, detail=f"App not registered: {scenario.app_key}"
            )

        # Load DT data needed
        # PoC: expect scenario payload contains start/end or use a default window elsewhere
        payload = scenario.payload_jsonld
        start = payload.get("start")
        end = payload.get("end")
        if not start or not end:
            raise HTTPException(
                status_code=400,
                detail="Scenario payload must include 'start' and 'end' ISO timestamps",
            )
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        df = load_timeseries(session, scenario.rec_id, start_dt, end_dt)
        if df.empty:
            raise HTTPException(
                status_code=404,
                detail="No materialized timeseries for scenario range. Call /materialize first.",
            )

        run = Run(
            run_id=run_id, scenario_id=scenario_id, model=req.model, status="running"
        )
        session.add(run)
        session.commit()

        # Execute
        result_jsonld = app.run(payload, df, options=req.options)
        # Attach JSON-LD contexts for responses
        result_jsonld = with_context(
            result_jsonld, AppRegistryHolder.jsonld_context_files
        )

        session.add(RunResult(run_id=run_id, results_jsonld=result_jsonld))
        run.status = "success"
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        return RunCreateResponse(run_id=run_id, status=run.status)
    except HTTPException:
        # update run status if already created
        raise
    except Exception as e:
        logger.exception(
            "Run failed", extra={"run_id": run_id, "scenario_id": scenario_id}
        )
        # best-effort persist failure
        try:
            run = session.exec(select(Run).where(Run.run_id == run_id)).one_or_none()
            if run:
                run.status = "failed"
                run.error = str(e)
                run.finished_at = datetime.utcnow()
                session.add(run)
                session.commit()
        except Exception:
            logger.exception("Failed to persist run failure", extra={"run_id": run_id})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/results", response_model=RunResultResponse)
def get_run_results(
    run_id: str,
    session: Session = Depends(get_session),
) -> RunResultResponse:
    row = session.exec(
        select(RunResult).where(RunResult.run_id == run_id)
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run result not found")
    return RunResultResponse(run_id=run_id, results=row.results_jsonld)


class AppRegistryHolder:
    registry: AppRegistry
    jsonld_context_files: list[str]
