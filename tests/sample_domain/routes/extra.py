# tests/sample_domain/routes/extra.py
"""A custom route module, shaped exactly as `.agents/playbooks/extending-a-domain.md`
prescribes: a module-level `router`, an optional `__prefix__` and `__tags__`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from celine.dt.api.context import Ctx, get_ctx

router = APIRouter()
__prefix__ = "/extra"
__tags__ = ["Extra"]


@router.get("/echo", operation_id="echo")
async def echo(ctx: Ctx = Depends(get_ctx)) -> dict:
    """Echo the resolved context back, to prove the entity scope reached this route."""
    return {
        "entity_id": ctx.entity.id,
        "domain": ctx.domain.name,
        "metadata": ctx.entity.metadata,
    }


@router.get("/via-fetch", operation_id="via_fetch")
async def via_fetch(ctx: Ctx = Depends(get_ctx)) -> dict:
    """Reach data the way the playbook says to: `ctx.fetch_value`, not the client.

    This also pins that `fetch_value` namespaces the id for the caller, so a custom
    route passes the *local* fetcher id.
    """
    result = await ctx.fetch_value("consumption")
    return {"count": result.count}
