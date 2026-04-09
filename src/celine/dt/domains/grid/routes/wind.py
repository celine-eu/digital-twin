# celine/dt/domains/grid/routes/wind.py
"""
Wind risk endpoints.

Charts ported:
  - Grid risks forecasts MT    → GET /wind/map
  - Grid wind forecast bosco   → GET /wind/bosco
  - Alert trends (donut)       → GET /wind/alert-distribution
  - Wind trend (KPI sparkline) → GET /wind/trend

Source tables (schema ds_dev_gold):
  grid_wind_risks  — wind risk per MT overhead segment (all conductor types except underground_cable)
                     is_vegetated_zone=true for segments passing through forested areas
  om_wind_gusts    — operational wind gust observations/forecast
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from celine.dt.domains.grid.dependencies import GridCtx, get_grid_ctx
from celine.dt.domains.grid.queries import (
    SCHEMA,
    _in_clause,
    apply_common_filters,
    rows_to_feature_collection,
)

__prefix__ = "/wind"
__tags__ = []

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /wind/map  — Grid risks forecasts MT
# Source: grid_wind_risks, conductor_type IN ('overhead_bare','overhead_insulated')
# ---------------------------------------------------------------------------

@router.get("/map", operation_id="wind_map")
async def wind_map(
    ctx: GridCtx = Depends(get_grid_ctx),
    dates: list[str] | None = Query(None),
    operational_unit: list[str] | None = Query(None),
    line_name: list[str] | None = Query(None),
    substation_name: list[str] | None = Query(None),
    risk_level: list[str] | None = Query(None),
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of overhead MT line segments coloured by wind risk."""
    clauses = [
        "WHERE conductor_type IN ('overhead_bare', 'overhead_insulated')",
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
    if risk_level:
        clauses.append(_in_clause("risk_level", risk_level))

    sql = f"""
        SELECT line_name, conductor_type, parent_substation_name, operational_unit,
               feeder_id, municipality,
               date::text AS date, risk_level, risk_color_hex,
               gust_excess, wind_speed_max, wind_gusts_max,
               feature_geojson
        FROM {SCHEMA}.grid_wind_risks
        {" ".join(clauses)}
        ORDER BY date DESC, line_name
    """
    try:
        rows = await ctx.domain.dataset_client.query(sql=sql, limit=10000, ctx=ctx)
    except Exception as exc:
        log.error("wind_map query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch wind map data")

    return rows_to_feature_collection(rows)


# ---------------------------------------------------------------------------
# GET /wind/bosco  — Grid wind forecast vegetated routes
# Source: grid_wind_risks WHERE is_vegetated_zone = true
# ---------------------------------------------------------------------------

@router.get("/bosco", operation_id="wind_bosco")
async def wind_bosco(
    ctx: GridCtx = Depends(get_grid_ctx),
    dates: list[str] | None = Query(None),
    operational_unit: list[str] | None = Query(None),
    line_name: list[str] | None = Query(None),
    substation_name: list[str] | None = Query(None),
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of overhead segments in vegetated zones, coloured by wind risk."""
    clauses = [
        "WHERE is_vegetated_zone = true",
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
        SELECT line_name, conductor_type, parent_substation_name, operational_unit, municipality,
               is_vegetated_zone, elevation_start_m, elevation_end_m,
               date::text AS date, risk_level, risk_color_hex,
               gust_excess, wind_speed_max, wind_gusts_max,
               feature_geojson
        FROM {SCHEMA}.grid_wind_risks
        {" ".join(clauses)}
        ORDER BY date DESC, line_name
    """
    try:
        rows = await ctx.domain.dataset_client.query(sql=sql, limit=10000, ctx=ctx)
    except Exception as exc:
        log.error("wind_bosco query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch bosco wind data")

    return rows_to_feature_collection(rows)


# ---------------------------------------------------------------------------
# GET /wind/alert-distribution  — Alert trends (donut)
# Source: grid_wind_risks, conductor_type = overhead (bare + insulated)
# ---------------------------------------------------------------------------

@router.get("/alert-distribution", operation_id="wind_alert_distribution")
async def wind_alert_distribution(
    ctx: GridCtx = Depends(get_grid_ctx),
    dates: list[str] | None = Query(None),
    operational_unit: list[str] | None = Query(None),
    line_name: list[str] | None = Query(None),
    substation_name: list[str] | None = Query(None),
) -> list[dict[str, Any]]:
    """COUNT of line-segment events per risk_level for wind (overhead lines)."""
    clauses = ["WHERE conductor_type IN ('overhead_bare', 'overhead_insulated')"]
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
        FROM {SCHEMA}.grid_wind_risks
        {" ".join(clauses)}
        GROUP BY risk_level
        ORDER BY events DESC
    """
    try:
        return await ctx.domain.dataset_client.query(sql=sql, limit=100, ctx=ctx)
    except Exception as exc:
        log.error("wind_alert_distribution query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch wind alert distribution")


# ---------------------------------------------------------------------------
# GET /wind/trend  — Wind trend KPI (fixed rolling window: now−1d → now+2d)
# Source: om_wind_gusts
# ---------------------------------------------------------------------------

@router.get("/trend", operation_id="wind_trend")
async def wind_trend(
    ctx: GridCtx = Depends(get_grid_ctx),
) -> list[dict[str, Any]]:
    """Daily MAX(gust_excess) over the rolling window now−1d → now+2d."""
    sql = f"""
        SELECT date::date::text AS date, MAX(gust_excess) AS value
        FROM {SCHEMA}.om_wind_gusts
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
          AND date <= CURRENT_DATE + INTERVAL '2 days'
        GROUP BY date::date
        ORDER BY date
    """
    try:
        return await ctx.domain.dataset_client.query(sql=sql, limit=10, ctx=ctx)
    except Exception as exc:
        log.error("wind_trend query failed: %s", exc)
        raise HTTPException(502, "Failed to fetch wind trend")
