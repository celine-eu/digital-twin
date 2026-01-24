from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

from celine.dt.core.dt import DT

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_dt(request: Request) -> DT:
    dt = getattr(request.app.state, "dt", None)
    if dt is None:
        logger.error("DT runtime not initialized")
        raise HTTPException(status_code=500, detail="DT runtime not initialized")
    return cast(DT, dt)


@router.get("")
async def list_apps(request: Request) -> list[dict[str, str]]:
    """List all registered DT apps with their versions."""
    dt = _get_dt(request)
    return dt.list_apps()


@router.post("/{app_key}/run")
async def run_app(app_key: str, payload: dict[str, Any], request: Request) -> Any:
    """Execute a DT app.

    The API layer is a thin gate:
      - creates a per-request RunContext from the app-scoped DT
      - delegates to the DT runner
    """
    dt = _get_dt(request)
    context = dt.create_context(request=request, request_scope={})

    try:
        return await dt.run_app(app_key=app_key, payload=payload, context=context)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to execute app '%s'", app_key)
        raise HTTPException(status_code=500, detail="App execution failed") from exc


@router.get("/{app_key}/describe")
async def describe_app(app_key: str, request: Request) -> dict:
    """Describe a DT app: metadata + input/output schemas."""
    dt = _get_dt(request)
    try:
        return dt.describe_app(app_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
