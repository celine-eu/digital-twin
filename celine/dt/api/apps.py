from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

from celine.dt.core.context import RunContext
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.registry import DTRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_apps(request: Request) -> list[dict[str, str]]:
    """
    List all registered DT apps with their versions.
    """
    registry = getattr(request.app.state, "registry", None)

    if registry is None:
        raise HTTPException(
            status_code=500,
            detail="DT runtime not initialized",
        )

    return registry.list_apps()


@router.post("/{app_key}/run")
async def run_app(
    app_key: str,
    payload: dict[str, Any],
    request: Request,
) -> Any:
    """
    Generic DT app execution endpoint.

    Responsibilities:
      - extract runtime dependencies from FastAPI state
      - build RunContext
      - delegate execution to DTAppRunner
    """
    registry: DTRegistry | None = getattr(request.app.state, "registry", None)
    runner: DTAppRunner | None = getattr(request.app.state, "runner", None)

    if registry is None or runner is None:
        logger.error("DT runtime not initialized correctly")
        raise HTTPException(
            status_code=500,
            detail="DT runtime not initialized",
        )

    context = RunContext.create(
        datasets=request.app.state.dataset_client,
        state=request.app.state.state_store,
        request=request,
        token_provider=request.app.state.token_provider,
    )

    try:
        return await runner.run(
            registry=registry,
            app_key=app_key,
            payload=payload,
            context=context,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # input validation / domain errors
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to execute app '%s'", app_key)
        raise HTTPException(
            status_code=500,
            detail="App execution failed",
        ) from exc


@router.get("/{app_key}/describe")
async def describe_app(app_key: str, request: Request) -> dict:
    """
    Describe a DT app: metadata + input/output schemas.

    This endpoint is purely introspective and has no side effects.
    """
    registry: DTRegistry = cast(
        DTRegistry, getattr(request.app.state, "registry", None)
    )

    if registry is None:
        raise HTTPException(
            status_code=500,
            detail="DT runtime not initialized",
        )

    try:
        return registry.describe_app(app_key)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
