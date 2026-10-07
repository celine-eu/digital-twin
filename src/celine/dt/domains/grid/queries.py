# celine/dt/domains/grid/queries.py
"""
SQL builder helpers for grid resilience queries.

Values interpolated into SQL are string-quoted with single-quote escaping.
"""
from __future__ import annotations

import json
from typing import Any

SCHEMA = "ds_dev_gold"


# ---------------------------------------------------------------------------
# Safe SQL construction
# ---------------------------------------------------------------------------

def _quote(v: str) -> str:
    """Single-quote a string value, escaping internal quotes."""
    return "'" + str(v).replace("'", "''") + "'"


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
