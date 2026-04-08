# celine/dt/domains/grid/dependencies.py
from __future__ import annotations

from typing import cast

from fastapi import Depends, HTTPException

from celine.dt.api.context import Ctx, get_ctx_auth
from celine.dt.contracts.entity import EntityInfo
from celine.dt.domains.grid.domain import GridDomain

GridCtx = Ctx[GridDomain, EntityInfo]


async def get_grid_ctx(ctx: Ctx = Depends(get_ctx_auth)) -> GridCtx:
    if not isinstance(ctx.domain, GridDomain):
        raise HTTPException(500, "Invalid domain for grid context")
    return cast(GridCtx, ctx)
