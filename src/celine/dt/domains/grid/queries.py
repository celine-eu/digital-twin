# celine/dt/domains/grid/queries.py
"""
SQL builder helpers for grid resilience queries.

All user-supplied filter values are string-quoted with single-quote escaping.
Date values are validated against ISO-8601 format before interpolation.
"""
from __future__ import annotations

import json
import re
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMA = "ds_dev_gold"


# ---------------------------------------------------------------------------
# Safe SQL construction
# ---------------------------------------------------------------------------

def _quote(v: str) -> str:
    """Single-quote a string value, escaping internal quotes."""
    return "'" + str(v).replace("'", "''") + "'"


def _in_clause(col: str, values: list[str]) -> str:
    return f"AND {col} IN ({', '.join(_quote(v) for v in values)})"


def _date_in_clause(col: str, dates: list[str]) -> str:
    for d in dates:
        if not _DATE_RE.match(d):
            raise ValueError(f"Invalid date format: {d!r}. Expected YYYY-MM-DD.")
    return f"AND {col}::date IN ({', '.join(_quote(d) for d in dates)})"


def apply_common_filters(
    clauses: list[str],
    *,
    dates: list[str] | None,
    operational_unit: list[str] | None,
    line_name: list[str] | None,
    substation_name: list[str] | None,
) -> None:
    """Append optional filter clauses in-place."""
    if dates:
        clauses.append(_date_in_clause("date", dates))
    if operational_unit:
        clauses.append(_in_clause("operational_unit", operational_unit))
    if line_name:
        clauses.append(_in_clause("line_name", line_name))
    if substation_name:
        clauses.append(_in_clause("substation_name", substation_name))


# ---------------------------------------------------------------------------
# GeoJSON assembly
# ---------------------------------------------------------------------------

def rows_to_feature_collection(rows: list[dict[str, Any]], geom_col: str = "feature_geojson") -> dict:
    features = []
    for row in rows:
        raw_geom = row.get(geom_col)
        if not raw_geom:
            continue
        try:
            geom = json.loads(raw_geom) if isinstance(raw_geom, str) else raw_geom
        except (ValueError, TypeError):
            continue

        # If the stored value is already a Feature, pull its geometry out.
        if geom.get("type") == "Feature":
            geometry = geom.get("geometry")
            stored_props = geom.get("properties") or {}
        else:
            geometry = geom
            stored_props = {}

        props = {k: v for k, v in row.items() if k != geom_col}
        props.update(stored_props)

        features.append({"type": "Feature", "geometry": geometry, "properties": props})

    return {"type": "FeatureCollection", "features": features}
