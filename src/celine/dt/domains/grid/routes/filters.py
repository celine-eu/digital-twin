# celine/dt/domains/grid/routes/filters.py
"""
Filter metadata endpoint.

  GET /filters  — distinct topology values for UI filter autocomplete

Source table (schema ds_dev_gold):
  grid_network_topology  — distinct line/substation/unit/municipality combinations
                           rebuilt on monthly topology cadence
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from celine.dt.domains.grid.dependencies import GridCtx, get_grid_ctx
from celine.dt.domains.grid.queries import SCHEMA

__prefix__ = "/filters"
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("", operation_id="it_grid_filters")
async def get_filters(
    ctx: GridCtx = Depends(get_grid_ctx),
) -> dict[str, list[str]]:
    """Distinct topology values for UI filter autocomplete.

    Returns one object with four arrays — a single DB round-trip for all
    filter dimensions. Values come from silver_grid_ac_line_segment (via
    grid_network_topology), so filter options are always complete regardless
    of weather data availability.
    """
    sql = f"""
        SELECT
            array_agg(DISTINCT parent_substation_name ORDER BY parent_substation_name)
                FILTER (WHERE parent_substation_name IS NOT NULL) AS parent_substations,
            array_agg(DISTINCT line_name ORDER BY line_name)
                FILTER (WHERE line_name IS NOT NULL) AS lines,
            array_agg(DISTINCT operational_unit ORDER BY operational_unit)
                FILTER (WHERE operational_unit IS NOT NULL) AS operational_units,
            array_agg(DISTINCT municipality ORDER BY municipality)
                FILTER (WHERE municipality IS NOT NULL) AS municipalities
        FROM {SCHEMA}.grid_network_topology
    """
    try:
        rows = await ctx.domain.dataset_client.query(sql=sql, limit=1, ctx=ctx)
    except Exception as exc:
        log.error("get_filters query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch filter options")

    return rows[0] if rows else {
        "parent_substations": [],
        "lines": [],
        "operational_units": [],
        "municipalities": [],
    }
