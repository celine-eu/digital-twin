from __future__ import annotations

import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dt.core.registry import AppRegistry
from celine.dt.db.models import Scenario as ScenarioModel
from celine.dt.api.schemas import ScenarioCreateRequest, ScenarioCreateResponse
from celine.dt.api.exceptions import NotFound

logger = logging.getLogger(__name__)

async def create_scenario(
    *,
    session: AsyncSession,
    registry: AppRegistry,
    rec_id: str,
    req: ScenarioCreateRequest,
) -> ScenarioCreateResponse:
    app = registry.apps.get(req.app_key)
    if not app:
        raise NotFound(f"Unknown app_key '{req.app_key}'")

    payload = app.create_scenario(req.payload)
    scenario_id = f"scn-{uuid.uuid4().hex}"

    row = ScenarioModel(
        scenario_id=scenario_id,
        rec_id=rec_id,
        app_key=req.app_key,
        payload_jsonld=payload,
    )
    session.add(row)
    await session.commit()

    return ScenarioCreateResponse(
        scenario_id=scenario_id,
        app_key=req.app_key,
        rec_id=rec_id,
        payload=payload,
    )

async def get_scenario(
    *,
    session: AsyncSession,
    scenario_id: str,
) -> ScenarioModel:
    res = await session.execute(select(ScenarioModel).where(ScenarioModel.scenario_id == scenario_id))
    row = res.scalars().one_or_none()
    if not row:
        raise NotFound("Scenario not found")
    return row
