# celine/dt/domains/grid/routes/heat.py
"""
Heat risk endpoints.

Charts ported:
  - Heat risk MT               → GET /heat/map
  - Heat Alert trends (donut)  → GET /heat/alert-distribution
  - Max temperature (KPI)      → GET /heat/trend

Source tables (schema ds_dev_gold):
  grid_heat_risks_linee  — heat risk per MT line segment (underground cables)
  om_heat_risk           — operational heat observations/forecast
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from celine.dt.domains.grid.dependencies import GridCtx, get_grid_ctx
from celine.dt.domains.grid.queries import (
    SCHEMA,
    apply_common_filters,
    rows_to_feature_collection,
)

__prefix__ = "/heat"
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /heat/map  — Heat risk MT
# Source: grid_heat_risks_linee, conductor_type = 'underground_cable'
# ---------------------------------------------------------------------------

@router.get("/map", operation_id="heat_map")
async def heat_map(
    ctx: GridCtx = Depends(get_grid_ctx),
    dates: list[str] | None = Query(None),
    operational_unit: list[str] | None = Query(None),
    line_name: list[str] | None = Query(None),
    substation_name: list[str] | None = Query(None),
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of underground MT cable segments coloured by heat risk."""
    clauses = [
        "WHERE conductor_type = 'underground_cable'",
        "AND feature_geojson IS NOT NULL",
    ]
    try:
        apply_common_filters(
            clauses,
            dates=dates,
            operational_unit=operational_unit,
            line_name=line_name,
            substation_name=substation_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    sql = f"""
        SELECT line_name, conductor_type, substation_name, operational_unit,
               feeder_id, municipality,
               date::text AS date, risk_level, risk_color_hex,
               temp_max_c, p90_threshold, consecutive_heat_days,
               altitude_band, forecast_model,
               feature_geojson
        FROM {SCHEMA}.grid_heat_risks_linee
        {" ".join(clauses)}
        ORDER BY date DESC, line_name
    """
    try:
        rows = await ctx.domain.dataset_client.query(sql=sql, limit=10000, ctx=ctx)
    except Exception as exc:
        log.error("heat_map query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch heat map data")

    return rows_to_feature_collection(rows)


# ---------------------------------------------------------------------------
# GET /heat/alert-distribution  — Heat Alert trends (donut)
# Source: grid_heat_risks_linee, conductor_type = 'underground_cable'
# ---------------------------------------------------------------------------

@router.get("/alert-distribution", operation_id="heat_alert_distribution")
async def heat_alert_distribution(
    ctx: GridCtx = Depends(get_grid_ctx),
    dates: list[str] | None = Query(None),
    operational_unit: list[str] | None = Query(None),
    line_name: list[str] | None = Query(None),
    substation_name: list[str] | None = Query(None),
) -> list[dict[str, Any]]:
    """COUNT of line-segment events per risk_level for heat (underground cables)."""
    clauses = ["WHERE conductor_type = 'underground_cable'"]
    try:
        apply_common_filters(
            clauses,
            dates=dates,
            operational_unit=operational_unit,
            line_name=line_name,
            substation_name=substation_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    sql = f"""
        SELECT risk_level, COUNT(*) AS events
        FROM {SCHEMA}.grid_heat_risks_linee
        {" ".join(clauses)}
        GROUP BY risk_level
        ORDER BY events DESC
    """
    try:
        return await ctx.domain.dataset_client.query(sql=sql, limit=100, ctx=ctx)
    except Exception as exc:
        log.error("heat_alert_distribution query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch heat alert distribution")


# ---------------------------------------------------------------------------
# GET /heat/trend  — Max temperature KPI (fixed rolling window: now−3d → now+2d)
# Source: om_heat_risk
# ---------------------------------------------------------------------------

@router.get("/trend", operation_id="heat_trend")
async def heat_trend(
    ctx: GridCtx = Depends(get_grid_ctx),
) -> list[dict[str, Any]]:
    """Daily MAX(temp_max_c) over the rolling window now−3d → now+2d."""
    sql = f"""
        SELECT date::date::text AS date, MAX(temp_max_c) AS value
        FROM {SCHEMA}.om_heat_risk
        WHERE date >= CURRENT_DATE - INTERVAL '3 days'
          AND date <= CURRENT_DATE + INTERVAL '2 days'
        GROUP BY date::date
        ORDER BY date
    """
    try:
        return await ctx.domain.dataset_client.query(sql=sql, limit=10, ctx=ctx)
    except Exception as exc:
        log.error("heat_trend query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch heat trend")
