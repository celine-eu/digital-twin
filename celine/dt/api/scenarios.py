from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from celine.dt.core.db import get_session
from celine.dt.core.registry import AppRegistry
from celine.dt.simulation.models import Scenario
from celine.dt.api.schemas import ScenarioCreateRequest, ScenarioCreateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["core-scenarios"])


@router.post("/recs/{rec_id}/scenarios", response_model=ScenarioCreateResponse)
def create_scenario(
    rec_id: str,
    req: ScenarioCreateRequest,
    session: Session = Depends(get_session),
    registry: AppRegistry = Depends(lambda: AppRegistryHolder.registry),
) -> ScenarioCreateResponse:
    try:
        app = registry.apps.get(req.app_key)
        if not app:
            raise HTTPException(
                status_code=404, detail=f"Unknown app_key '{req.app_key}'"
            )

        payload = app.create_scenario(req.payload)
        scenario_id = f"scn-{uuid.uuid4().hex}"

        row = Scenario(
            scenario_id=scenario_id,
            rec_id=rec_id,
            app_key=req.app_key,
            payload_jsonld=payload,
        )
        session.add(row)
        session.commit()
        return ScenarioCreateResponse(
            scenario_id=scenario_id, app_key=req.app_key, rec_id=rec_id, payload=payload
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Scenario creation failed", extra={"rec_id": rec_id, "app_key": req.app_key}
        )
        raise HTTPException(status_code=500, detail=str(e))


class AppRegistryHolder:
    registry: AppRegistry
