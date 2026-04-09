# celine/dt/domains/grid/routes/substations.py
"""
Secondary substation endpoints (CIM: Substation).

  GET /substations/map  — static GeoJSON layer of all secondary substations

Source table (schema ds_dev_gold):
  grid_substations  — secondary substations with pre-computed feature_geojson
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from celine.dt.domains.grid.dependencies import GridCtx, get_grid_ctx
from celine.dt.domains.grid.queries import SCHEMA, rows_to_feature_collection

__prefix__ = "/substations"
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /substations/map  — static secondary substation layer
# ---------------------------------------------------------------------------

@router.get("/map", operation_id="it_grid_substations_map")
async def substations_map(
    ctx: GridCtx = Depends(get_grid_ctx),
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of all secondary substations."""
    sql = f"""
        SELECT asset_id, name, label_id, label, line_name,
               feeder_id, parent_substation_name, operational_unit, municipality,
               longitude, latitude, feature_geojson
        FROM {SCHEMA}.grid_substations
        WHERE feature_geojson IS NOT NULL
        ORDER BY name
    """
    try:
        rows = await ctx.domain.dataset_client.query(sql=sql, limit=10000, ctx=ctx)
    except Exception as exc:
        log.error("substations_map query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch substations map data")

    return rows_to_feature_collection(rows)
