# celine/dt/core/domain/routes/ontology.py
"""
Built-in ontology routes.

Mounted automatically for every domain under ``/{entity_id}/ontology/``.
Endpoints return JSON-LD documents (``application/ld+json``) by fetching
raw rows via the values infrastructure and transforming them through the
CELINE ontology mapper.

Auth/authz follows the same model as all other built-in routes:
``get_ctx_auth`` requires a valid JWT token and resolves the entity.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.core.domain.base import DTDomain
from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.executor import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ontology")

JSONLD_MEDIA_TYPE = "application/ld+json"


# -- Schema -------------------------------------------------------------------


class OntologySpecDescriptor(BaseModel):
    """Metadata about a single ontology spec, for the listing endpoint."""

    id: str
    description: str
    fetcher_ids: list[str]


# -- Helpers ------------------------------------------------------------------


def _get_spec_or_404(domain: DTDomain, spec_id: str):
    spec = domain.get_ontology_spec(spec_id)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ontology spec '{spec_id}' not found in domain '{domain.name}'.",
        )
    return spec


# -- Routes -------------------------------------------------------------------


@router.get(
    "",
    response_model=list[OntologySpecDescriptor],
    operation_id="list_ontology_specs",
)
async def list_ontology_specs(
    ctx: Ctx = Depends(get_ctx_auth),
) -> list[OntologySpecDescriptor]:
    """List available ontology concept views for this entity's domain."""
    domain: DTDomain = ctx.domain
    return [
        OntologySpecDescriptor(
            id=spec.id,
            description=spec.description,
            fetcher_ids=[b.fetcher_id for b in spec.bindings],
        )
        for spec in domain.get_ontology_specs()
    ]


@router.get(
    "/{spec_id}",
    operation_id="fetch_ontology_get",
    response_class=JSONResponse,
)
async def fetch_ontology_get(
    spec_id: str,
    request: Request,
    ctx: Ctx = Depends(get_ctx_auth),
    limit: int | None = Query(default=None, ge=0),
    offset: int | None = Query(default=None, ge=0),
) -> JSONResponse:
    """Fetch an ontology concept view as a JSON-LD document.

    Query parameters (other than ``limit`` and ``offset``) are forwarded
    as payload to each underlying value fetcher.
    """
    domain: DTDomain = ctx.domain
    entity: EntityInfo = ctx.entity

    spec = _get_spec_or_404(domain, spec_id)

    qp = request.query_params
    payload: dict[str, Any] = {}
    for k in qp.keys():
        vals = qp.getlist(k)
        payload[k] = vals[0] if len(vals) == 1 else vals
    payload.pop("limit", None)
    payload.pop("offset", None)

    try:
        document = await domain.infra.ontology_service.fetch_as_jsonld(
            spec=spec,
            entity=entity,
            payload=payload,
            limit=limit,
            offset=offset,
            ctx=ctx,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict())
    except Exception as exc:
        logger.error(
            "fetch_ontology_get(%s/%s) failed: %s", entity.domain_name, entity.id, exc
        )
        raise HTTPException(status_code=500, detail="Internal server error")

    return JSONResponse(content=document, media_type=JSONLD_MEDIA_TYPE)


class OntologyRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/{spec_id}",
    operation_id="fetch_ontology_post",
    response_class=JSONResponse,
)
async def fetch_ontology_post(
    spec_id: str,
    body: OntologyRequest,
    ctx: Ctx = Depends(get_ctx_auth),
) -> JSONResponse:
    """Fetch an ontology concept view as a JSON-LD document (POST/body variant)."""
    domain: DTDomain = ctx.domain
    entity: EntityInfo = ctx.entity

    spec = _get_spec_or_404(domain, spec_id)

    payload = dict(body.payload)
    limit: int | None = payload.pop("limit", None)
    offset: int | None = payload.pop("offset", None)

    try:
        document = await domain.infra.ontology_service.fetch_as_jsonld(
            spec=spec,
            entity=entity,
            payload=payload,
            limit=limit,
            offset=offset,
            ctx=ctx,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict())
    except Exception as exc:
        logger.error(
            "fetch_ontology_post(%s/%s) failed: %s", entity.domain_name, entity.id, exc
        )
        raise HTTPException(status_code=500, detail="Internal server error")

    return JSONResponse(content=document, media_type=JSONLD_MEDIA_TYPE)
