from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request

from celine.dt.core.dt import DT
from celine.dt.core.values.executor import ValidationError
from celine.dt.core.values.coercion import coerce_params, CoercionError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_dt(request: Request) -> DT:
    dt = getattr(request.app.state, "dt", None)
    if dt is None:
        logger.error("DT runtime not initialized")
        raise HTTPException(status_code=500, detail="DT runtime not initialized")
    return cast(DT, dt)


@router.get("")
async def list_values(request: Request) -> list[dict[str, Any]]:
    """List all registered value fetchers."""
    dt = _get_dt(request)
    return dt.values.list()


@router.get("/{fetcher_id}/describe")
async def describe_value(fetcher_id: str, request: Request) -> dict[str, Any]:
    """Describe a value fetcher: metadata + payload schema."""
    dt = _get_dt(request)
    try:
        return dt.values.describe(fetcher_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")


@router.get("/{fetcher_id}")
async def get_value(
    fetcher_id: str,
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """Fetch values using query parameters."""
    dt = _get_dt(request)

    try:
        descriptor = dt.values.get_descriptor(fetcher_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")

    reserved = {"limit", "offset"}
    query_params = {k: v for k, v in request.query_params.items() if k not in reserved}

    try:
        payload = coerce_params(query_params, descriptor.spec.payload_schema)
    except CoercionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        result = await dt.values.fetch(
            fetcher_id=fetcher_id,
            payload=payload,
            limit=limit,
            offset=offset,
        )
        return result.to_dict()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Fetch failed for '%s'", fetcher_id)
        raise HTTPException(status_code=500, detail="Fetch operation failed")


@router.post("/{fetcher_id}")
async def post_value(
    fetcher_id: str,
    payload: dict[str, Any],
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """Fetch values using JSON payload."""
    dt = _get_dt(request)

    try:
        _ = dt.values.get_descriptor(fetcher_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Fetcher '{fetcher_id}' not found")

    try:
        result = await dt.values.fetch(
            fetcher_id=fetcher_id,
            payload=payload,
            limit=limit,
            offset=offset,
        )
        return result.to_dict()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Fetch failed for '%s'", fetcher_id)
        raise HTTPException(status_code=500, detail="Fetch operation failed")
