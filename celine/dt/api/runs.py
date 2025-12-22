from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.adapters.factory import get_dataset_adapter_for_app
from celine.dt.core.config import settings
from celine.dt.core.jsonld import with_context
from celine.dt.core.registry import AppRegistry
from celine.dt.db.models import Scenario as ScenarioModel, Run as RunModel, RunResult as RunResultModel
from celine.dt.api.schemas import RunCreateRequest, RunCreateResponse, RunResultResponse
from celine.dt.api.exceptions import NotFound, BadRequest

logger = logging.getLogger(__name__)

async def create_run(
    *,
    session: AsyncSession,
    registry: AppRegistry,
    jsonld_context_files: list[str],
    scenario_id: str,
    req: RunCreateRequest,
) -> RunCreateResponse:
    run_id = f"run-{uuid.uuid4().hex}"

    res = await session.execute(select(ScenarioModel).where(ScenarioModel.scenario_id == scenario_id))
    scenario = res.scalars().one_or_none()
    if not scenario:
        raise NotFound("Scenario not found")

    app = registry.apps.get(scenario.app_key)
    if not app:
        raise NotFound(f"App not registered: {scenario.app_key}")

    payload = scenario.payload_jsonld or {}
    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        raise BadRequest("Scenario payload must include 'start' and 'end' ISO timestamps")

    start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    granularity = payload.get("granularity") or settings.default_granularity

    run_row = RunModel(run_id=run_id, scenario_id=scenario_id, model=req.model, status="running")
    session.add(run_row)
    await session.commit()

    try:
        adapter = get_dataset_adapter_for_app(scenario.app_key)
        df = await app.fetch_inputs(adapter, scenario.rec_id, start_dt, end_dt, granularity)
        df = await app.materialize(df)

        if df.empty:
            raise NotFound("No materialized timeseries for scenario range")

        result_jsonld = await app.run(scenario, df, options=req.options)
        result_jsonld = with_context(result_jsonld, jsonld_context_files)

        session.add(RunResultModel(run_id=run_id, results_jsonld=result_jsonld))
        run_row.status = "success"
        run_row.finished_at = datetime.now(tz=timezone.utc)
        session.add(run_row)
        await session.commit()
        return RunCreateResponse(run_id=run_id, status=run_row.status)

    except Exception as e:
        logger.exception("Run failed", extra={"run_id": run_id, "scenario_id": scenario_id})
        try:
            run_row.status = "failed"
            run_row.error = str(e)
            run_row.finished_at = datetime.now(tz=timezone.utc)
            session.add(run_row)
            await session.commit()
        except Exception:
            logger.exception("Failed to persist run failure", extra={"run_id": run_id})
        raise

async def get_run_results(
    *,
    session: AsyncSession,
    run_id: str,
) -> RunResultResponse:
    res = await session.execute(select(RunResultModel).where(RunResultModel.run_id == run_id))
    row = res.scalars().one_or_none()
    if not row:
        raise NotFound("Run result not found")
    return RunResultResponse(run_id=run_id, results=row.results_jsonld)
