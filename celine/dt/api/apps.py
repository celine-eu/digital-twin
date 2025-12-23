from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{app_key}/run")
async def run_app(app_key: str, payload: dict[str, Any], request: Request) -> Any:
    """Generic app runner.

    Flow:
      1) If an InputMapper exists for `app_key`, map payload -> app inputs
      2) Run the app
      3) If an OutputMapper exists for `app_key`, map output -> response
    """
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    app = registry.apps.get(app_key)
    if app is None:
        raise HTTPException(status_code=404, detail=f"Unknown app '{app_key}'")

    try:
        mapper = registry.input_mappers.get(app_key)
        inputs = mapper.map(payload) if mapper else payload

        result = await app.run(inputs, request=request)

        out_mapper = registry.output_mappers.get(app_key)
        return out_mapper.map(result) if out_mapper else result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("App run failed: %s", app_key)
        raise HTTPException(status_code=500, detail=str(e)) from e
