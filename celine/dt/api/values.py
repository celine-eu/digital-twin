# celine/dt/api/values.py
"""
API endpoints for value fetchers.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from celine.dt.core.values.registry import ValuesRegistry
from celine.dt.core.values.executor import ValuesFetcher, ValidationError
from celine.dt.core.values.coercion import coerce_params, CoercionError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_values_registry(request: Request) -> ValuesRegistry:
    """Get values registry from app state or raise 500."""
    registry = getattr(request.app.state, "values_registry", None)

    if registry is None:
        logger.error("Values registry not initialized")
        raise HTTPException(
            status_code=500,
            detail="Values registry not initialized",
        )

    return registry


def _get_values_fetcher(request: Request) -> ValuesFetcher:
    """Get values fetcher from app state or raise 500."""
    fetcher = getattr(request.app.state, "values_fetcher", None)

    if fetcher is None:
        logger.error("Values fetcher not initialized")
        raise HTTPException(
            status_code=500,
            detail="Values fetcher not initialized",
        )

    return fetcher


@router.get("")
async def list_values(request: Request) -> list[dict[str, Any]]:
    """
    List all registered value fetchers.

    Returns:
        List of fetcher metadata: [{id, client, has_payload_schema}, ...]
    """
    registry = _get_values_registry(request)
    return registry.list()


@router.get("/{fetcher_id}/describe")
async def describe_value(fetcher_id: str, request: Request) -> dict[str, Any]:
    """
    Describe a value fetcher: metadata + payload schema.

    Args:
        fetcher_id: The fetcher identifier

    Returns:
        Fetcher description including payload schema
    """
    registry = _get_values_registry(request)

    try:
        return registry.describe(fetcher_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Fetcher '{fetcher_id}' not found",
        )


@router.get("/{fetcher_id}")
async def get_value(
    fetcher_id: str,
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """
    Fetch values using query parameters.

    Query parameters are coerced to types based on the fetcher's payload schema.
    Reserved parameters: limit, offset.

    Args:
        fetcher_id: The fetcher identifier
        limit: Override default result limit
        offset: Override default offset for pagination

    Returns:
        {items: [...], limit: N, offset: M, count: K}
    """
    registry = _get_values_registry(request)
    fetcher = _get_values_fetcher(request)

    # Get fetcher descriptor
    try:
        descriptor = registry.get(fetcher_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Fetcher '{fetcher_id}' not found",
        )

    # Extract query params (exclude reserved ones)
    reserved = {"limit", "offset"}
    query_params = {
        k: v
        for k, v in request.query_params.items()
        if k not in reserved
    }

    # Coerce params based on schema
    try:
        payload = coerce_params(query_params, descriptor.spec.payload_schema)
    except CoercionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # Execute fetch
    try:
        result = await fetcher.fetch(
            descriptor=descriptor,
            payload=payload,
            limit=limit,
            offset=offset,
        )
        return result.to_dict()
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Fetch failed for '%s'", fetcher_id)
        raise HTTPException(
            status_code=500,
            detail="Fetch operation failed",
        )


@router.post("/{fetcher_id}")
async def post_value(
    fetcher_id: str,
    payload: dict[str, Any],
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """
    Fetch values using JSON payload.

    Payload is validated against the fetcher's JSON Schema (if defined).

    Args:
        fetcher_id: The fetcher identifier
        payload: JSON body with parameters
        limit: Override default result limit
        offset: Override default offset for pagination

    Returns:
        {items: [...], limit: N, offset: M, count: K}
    """
    registry = _get_values_registry(request)
    fetcher = _get_values_fetcher(request)

    # Get fetcher descriptor
    try:
        descriptor = registry.get(fetcher_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Fetcher '{fetcher_id}' not found",
        )

    # Execute fetch (validation happens inside)
    try:
        result = await fetcher.fetch(
            descriptor=descriptor,
            payload=payload,
            limit=limit,
            offset=offset,
        )
        return result.to_dict()
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Fetch failed for '%s'", fetcher_id)
        raise HTTPException(
            status_code=500,
            detail="Fetch operation failed",
        )
