"""Reference-boundary fetchers shared by every energy-community locale (ADR-0003).

Two questions about published reference boundaries, for Italy the GSE conventional
primary-substation areas (one shape per substation code):

* ``boundary_at_point(source, lat, lon)``: the id of the boundary covering a point;
* ``boundary_shape(source, ids)``: the shapes of named boundaries, as GeoJSON.

``source`` is a closed enum. Each value selects its table through a Jinja branch
written below (REQ-1214); the value itself never reaches the statement. A branch
normalises its table to two columns, ``id`` and ``geometry`` (WGS 84), so a new
source is a new enum value plus a new branch, and the two queries do not change.

The community in the path does not scope the answer: the boundaries are open
reference data (ADR-0003). Both fetchers query dataset-api with the Digital Twin's
own service token (``identity="service"``, REQ-1125, REQ-1160), not the caller's
forwarded one, so a caller needs ``digital-twin.values.read`` and nothing on
dataset-api. The route still requires that authenticated caller.
"""

from __future__ import annotations

from celine.dt.contracts.values import ValueFetcherSpec

#: The closed ``source`` enum (REQ-1150). Adding a value without adding its branch to
#: ``_BOUNDARY_TABLE`` fails rendering; ``tests/test_boundary_fetchers.py`` holds the
#: two together.
BOUNDARY_SOURCES: tuple[str, ...] = ("gse_cabine_primarie",)

#: The most ids one ``boundary_shape`` request may name (REQ-1159). A community has a
#: handful of substations; this is headroom, not a target.
BOUNDARY_SHAPE_MAX_IDS = 100

#: ``ST_Simplify`` tolerance for ``boundary_shape``, in degrees because the shapes are
#: stored in EPSG:4326: 0.0001 deg is about 11 m north-south and 8 m east-west at 45 deg
#: north. The shapes are drawn on a community-scale map, where that is below a pixel,
#: and a primary-substation area is kilometres across. ``preserveCollapsed`` is TRUE so a
#: small shape is kept rather than simplified away.
BOUNDARY_SHAPE_TOLERANCE_DEG = 0.0001

#: Decimal digits kept in the GeoJSON coordinates: 6 is about 0.1 m, far below the
#: tolerance above, and keeps the payload small.
BOUNDARY_SHAPE_GEOJSON_DIGITS = 6

# The source -> table branch (REQ-1214). One literal branch per enum value, each
# reading its table as (id, geometry). There is deliberately no fallback: a value with
# no branch renders an undefined name, which the renderer refuses as a template error,
# so drift between the enum and the branches fails rather than reading some default
# table. The enum in each payload_schema refuses an unknown value with a 400 first.
_BOUNDARY_TABLE = """(
        {%- if source == "gse_cabine_primarie" %}
        SELECT cod_ac AS id, geometry FROM ds_dev_gold.gse_cabine_primarie
        {%- else %}
        {{ boundary_source_has_no_table }}
        {%- endif %}
    ) AS boundary"""


def _source_property() -> dict:
    return {
        "type": "string",
        "enum": list(BOUNDARY_SOURCES),
        "description": (
            "Reference boundary set. gse_cabine_primarie: the GSE conventional "
            "primary-substation areas; ids are substation codes (cod_ac)."
        ),
    }


def boundary_value_specs() -> list[ValueFetcherSpec]:
    """The two boundary fetchers, declared once for every energy-community locale."""

    return [
        # A point covered by a shape: ST_Intersects of a point and a polygon is true
        # exactly when the point lies in the polygon's interior or on its boundary, which
        # is ST_Covers for a point (REQ-1153: the edge is inside). ST_Covers itself is not
        # in dataset-api's allowlist; ST_Intersects is, and uses the GIST index the same
        # way. Of several covering shapes, the lowest id wins (REQ-1155): ORDER BY id with
        # limit=1. dataset-api applies LIMIT after the ORDER BY.
        ValueFetcherSpec(
            id="boundary_at_point",
            client="dataset_api",
            identity="service",  # REQ-1160: open reference data, the DT's own token
            query=f"""
                SELECT boundary.id
                FROM {_BOUNDARY_TABLE}
                WHERE ST_Intersects(
                    boundary.geometry,
                    ST_SetSRID(ST_Point(:lon, :lat), 4326)
                )
                ORDER BY boundary.id ASC
            """,
            limit=1,
            payload_schema={
                "type": "object",
                "required": ["source", "lat", "lon"],
                "additionalProperties": False,
                "properties": {
                    "source": _source_property(),
                    "lat": {
                        "type": "number",
                        "minimum": -90,
                        "maximum": 90,
                        "description": "Latitude, WGS 84 degrees",
                    },
                    "lon": {
                        "type": "number",
                        "minimum": -180,
                        "maximum": 180,
                        "description": "Longitude, WGS 84 degrees",
                    },
                },
            },
        ),
        # One row per requested id the source knows (REQ-1156/1157). An empty `ids`
        # takes the else branch and selects nothing, so no `IN ()` is ever sent
        # (REQ-1158, REQ-1235). One row per id, so `limit` equals `maxItems` (REQ-1159).
        ValueFetcherSpec(
            id="boundary_shape",
            client="dataset_api",
            identity="service",  # REQ-1160: open reference data, the DT's own token
            query=f"""
                SELECT
                    boundary.id,
                    ST_AsGeoJSON(
                        ST_Simplify(boundary.geometry, {BOUNDARY_SHAPE_TOLERANCE_DEG}, TRUE),
                        {BOUNDARY_SHAPE_GEOJSON_DIGITS}
                    ) AS geojson
                FROM {_BOUNDARY_TABLE}
                {{% if ids %}}
                WHERE boundary.id IN {{{{ ids | sql_list }}}}
                {{% else %}}
                WHERE FALSE
                {{% endif %}}
                ORDER BY boundary.id ASC
            """,
            limit=BOUNDARY_SHAPE_MAX_IDS,
            payload_schema={
                "type": "object",
                "required": ["source", "ids"],
                "additionalProperties": False,
                "properties": {
                    "source": _source_property(),
                    "ids": {
                        "type": "array",
                        "maxItems": BOUNDARY_SHAPE_MAX_IDS,
                        "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        "description": (
                            "Boundary ids to return. Unknown ids are absent from the "
                            "answer; an empty list answers no rows."
                        ),
                    },
                },
            },
        ),
    ]
