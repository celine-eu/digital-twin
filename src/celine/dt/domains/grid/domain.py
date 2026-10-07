# celine/dt/domains/grid/domain.py
"""
Grid resilience domain — weather-driven risk monitoring for MT distribution networks.

Route surface::

    /grid/{network_id}/substations/map

``network_id`` is the distribution system operator's organisation alias, the value every
grid table carries in ``dso_id``. Every query is narrowed to it (``dso_id = entity.id``):
the callers include services, which no dataset-api row filter narrows. Who may name a
network is checked first, in ``GridDomain.resolve_entity``.

Value fetchers (auto-generated /values/{id} GET + POST)::

    it-grid.filters     — distinct topology values + network extent (single aggregation row)
    it-grid.tile_index  — lightweight tile catalog for progressive shape loading
    it-grid.shapes      — static CIM asset topology (lines, substations, joints, thermal tier/margin), supports tile_ids filter for progressive loading
    it-grid.risks       — WARNING/ALERT risk rows by date, no geometry
    it-grid.risks_now   — WARNING/ALERT nowcasting risk rows (current observations, no date filter)
    it-grid.trendline   — daily risk percentage indicator per vector
    it-grid.risk_km     — length-weighted risk exposure per tratta / line / operational unit
    it-grid.tree_strike_spans — tree-strike exposure spans (static overlay, tile_ids filter)
    it-grid.risks_8h    — WARNING/ALERT rows per 8-hour window (intra-day view)
"""
from __future__ import annotations

import logging
from typing import ClassVar

from fastapi import HTTPException, Request

from celine.dt.api.audit import note_reason
from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.clients.dataset_api import DatasetSqlApiClient

logger = logging.getLogger(__name__)

_SCHEMA = "ds_dev_gold"

DSO_TYPE = "dso"
# A service reads any network with one of these scopes (celine-grid's own); a person
# reads only the networks of the DSO organisations they belong to.
GRID_SCOPES = ("grid.read", "grid.admin")
NETWORK_NOT_OWNED = "network_not_owned"
GRID_SCOPE_MISSING = "grid_scope_missing"


def dso_networks(user) -> list[str]:
    """The aliases of the caller's DSO organisations, sorted."""
    return sorted(
        org.alias
        for org in user.organizations
        if org.type == DSO_TYPE or org.has_attribute("type", DSO_TYPE)
    )

# Shared WHERE fragment of risk_km: dates plus the optional topology filters.
_RISK_KM_WHERE = """
    WHERE dso_id = {{ entity.id | sql_quote }}
    AND date::date IN {{ dates | sql_list }}
    {% if risk_vector %}
    AND risk_vector IN {{ risk_vector | sql_list }}
    {% endif %}
    {% if operational_unit %}
    AND operational_unit IN {{ operational_unit | sql_list }}
    {% endif %}
    {% if line_name %}
    AND line_name IN {{ line_name | sql_list }}
    {% endif %}
    {% if substation_name %}
    AND parent_substation_name IN {{ substation_name | sql_list }}
    {% endif %}
"""

# Aggregated km columns shared by the line and unit grains.
_RISK_KM_SUMS = """
    sum(km_total)      AS km_total,
    sum(km_alert)      AS km_alert,
    sum(km_warning)    AS km_warning,
    sum(km_normal)     AS km_normal,
    sum(km_escalated)  AS km_escalated,
    sum(km_tree_high)  AS km_tree_high,
    sum(km_tree_mid)   AS km_tree_mid,
    sum(km_thermal_high) AS km_thermal_high,
    sum(km_thermal_mid)  AS km_thermal_mid,
    max(metric_max)    AS metric_max,
    CASE
        WHEN bool_or(worst_level = 'ALERT')   THEN 'ALERT'
        WHEN bool_or(worst_level = 'WARNING') THEN 'WARNING'
        ELSE 'NORMAL'
    END AS worst_level,
    round((100.0 * (sum(km_alert) + 0.5 * sum(km_warning))
           / nullif(sum(km_total), 0))::numeric, 2)::double precision AS risk_index
"""

# min_level on aggregated grains is a HAVING over the group's worst level, so the
# km totals of a kept group are still the whole group.
_RISK_KM_HAVING = """
    {% if min_level == 'ALERT' %}
    HAVING bool_or(worst_level = 'ALERT')
    {% elif min_level == 'WARNING' %}
    HAVING bool_or(worst_level IN ('ALERT', 'WARNING'))
    {% endif %}
"""

_RISK_KM_QUERY = (
    """
    {% if level == 'unit' %}
    SELECT date::text AS date, risk_vector, 'unit' AS level,
           operational_unit,
           count(*) AS n_tratte,
           count(DISTINCT line_name) AS n_lines,
    """ + _RISK_KM_SUMS + """
    FROM __SCHEMA__.grid_risk_km
    """ + _RISK_KM_WHERE + """
    GROUP BY date, risk_vector, operational_unit
    """ + _RISK_KM_HAVING + """
    ORDER BY date, risk_vector, risk_index DESC NULLS LAST, operational_unit

    {% elif level == 'line' %}
    SELECT date::text AS date, risk_vector, 'line' AS level,
           line_name,
           string_agg(DISTINCT operational_unit, ',' ORDER BY operational_unit) AS operational_units,
           count(DISTINCT operational_unit) AS n_units,
           min(parent_substation_name) AS parent_substation_name,
           count(*) AS n_tratte,
    """ + _RISK_KM_SUMS + """
    FROM __SCHEMA__.grid_risk_km
    """ + _RISK_KM_WHERE + """
    GROUP BY date, risk_vector, line_name
    """ + _RISK_KM_HAVING + """
    ORDER BY date, risk_vector, risk_index DESC NULLS LAST, line_name

    {% else %}
    SELECT date::text AS date, risk_vector, 'tratta' AS level,
           operational_unit, line_name, municipality, conductor_type, segment_id,
           parent_substation_name, feeder_id, n_fragments,
           km_total, km_alert, km_warning, km_normal, km_escalated,
           km_tree_high, km_tree_mid, km_thermal_high, km_thermal_mid,
           metric_max, worst_level,
           risk_index::double precision AS risk_index
    FROM __SCHEMA__.grid_risk_km
    """ + _RISK_KM_WHERE + """
    {% if min_level == 'ALERT' %}
    AND worst_level = 'ALERT'
    {% elif min_level == 'WARNING' %}
    AND worst_level IN ('ALERT', 'WARNING')
    {% endif %}
    ORDER BY date, risk_vector, risk_index DESC NULLS LAST, line_name, municipality
    {% endif %}
    """
).replace("__SCHEMA__", _SCHEMA)


class GridDomain(DTDomain):
    """Grid resilience domain.

    Pure read-through domain: no participant/asset/ontology machinery.
    Surfaces filtered GeoJSON and aggregated risk data from ds_dev_gold tables.
    """

    domain_type: ClassVar[str] = "grid"
    route_prefix: ClassVar[str] = "/grid"
    entity_id_param: ClassVar[str] = "network_id"

    @property
    def dataset_client(self) -> DatasetSqlApiClient:
        return self.infra.clients_registry.get("dataset_api")

    async def resolve_entity(
        self, entity_id: str, request: Request
    ) -> EntityInfo | None:
        """Who may name a network: refused before any query is rendered.

        A person names only a network of a DSO organisation they belong to; no realm
        role widens that, platform-admin included (as celine-grid's policy). A service
        account names any network with a ``grid.*`` scope. Organisation presence decides
        which of the two the caller is: a client-credentials token carries none.
        """
        caller = getattr(request.state, "user", None)
        if caller is None:
            note_reason(request, "no_token")
            raise HTTPException(401, "Authentication required")
        if caller.organizations or not caller.is_service_account:
            if entity_id not in dso_networks(caller):
                note_reason(request, NETWORK_NOT_OWNED)
                raise HTTPException(403, "The network is not one of the caller's DSO organisations")
        elif not any(caller.has_scope(s) for s in GRID_SCOPES):
            note_reason(request, GRID_SCOPE_MISSING)
            raise HTTPException(403, "A service needs a grid scope to read a network")
        return EntityInfo(id=entity_id, domain_name=self.name)

    async def on_startup(self) -> None:
        logger.info(
            "GridDomain '%s' starting (type=%s, version=%s)",
            self.name,
            self.domain_type,
            self.version,
        )


class ITGridDomain(GridDomain):
    """Italian MT grid resilience domain."""

    name: ClassVar[str] = "it-grid"
    version: ClassVar[str] = "1.0.0"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [

            # ------------------------------------------------------------------
            # filters — distinct topology values + network bounding box
            # Single aggregation row; no payload required.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="filters",
                client="dataset_api",
                query=f"""
                    SELECT
                        array_agg(DISTINCT parent_substation_name ORDER BY parent_substation_name)
                            FILTER (WHERE parent_substation_name IS NOT NULL) AS parent_substations,
                        array_agg(DISTINCT asset_key ORDER BY asset_key)
                            FILTER (WHERE asset_type = 'ac_line_segment' AND asset_key IS NOT NULL) AS lines,
                        array_agg(DISTINCT operational_unit ORDER BY operational_unit)
                            FILTER (WHERE operational_unit IS NOT NULL) AS operational_units,
                        array_agg(DISTINCT municipality ORDER BY municipality)
                            FILTER (WHERE municipality IS NOT NULL) AS municipalities,
                        ST_XMin(ST_Extent(ST_Transform(geom, 4326))) AS extent_min_lng,
                        ST_YMin(ST_Extent(ST_Transform(geom, 4326))) AS extent_min_lat,
                        ST_XMax(ST_Extent(ST_Transform(geom, 4326))) AS extent_max_lng,
                        ST_YMax(ST_Extent(ST_Transform(geom, 4326))) AS extent_max_lat
                    FROM {_SCHEMA}.grid_shapes
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                """,
                limit=1,
            ),

            # ------------------------------------------------------------------
            # tile_index — lightweight tile catalog for progressive loading
            # Returns one row per 5 km tile with bbox polygon and segment count.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="tile_index",
                client="dataset_api",
                query=f"""
                    SELECT tile_id, tile_x, tile_y,
                           tile_bbox_geojson, segment_count
                    FROM {_SCHEMA}.grid_tile_index
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    ORDER BY tile_y, tile_x
                """,
                limit=500,
            ),

            # ------------------------------------------------------------------
            # shapes — static CIM asset topology, geometry only
            # Supports optional tile_ids filter for progressive loading.
            # Without tile_ids, returns all shapes (backward compatible).
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="shapes",
                client="dataset_api",
                query=f"""
                    SELECT segment_id, asset_type, asset_key, name, conductor_type,
                           parent_substation_name, operational_unit, municipality,
                           feeder_id, length_m, is_vegetated_zone,
                           strike_tree_tier, strike_tree_multiplier,
                           strike_density_per_km,
                           strike_km_high, strike_km_mid, strike_km_low,
                           voltage_class, label, label_id,
                           thermal_tier, thermal_margin_c, thermal_theta_max_c,
                           thermal_insulation, is_asphalt, anno_posa, technology,
                           m_r_critico,
                           feature_geojson
                    FROM {_SCHEMA}.grid_shapes
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    {{% if asset_type %}}
                    AND asset_type IN {{{{ asset_type | sql_list }}}}
                    {{% endif %}}
                    {{% if tile_ids %}}
                    AND segment_id IN (
                        SELECT segment_id FROM {_SCHEMA}.grid_tiles
                        WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                        AND tile_id IN {{{{ tile_ids | sql_list }}}}
                    )
                    {{% endif %}}
                    ORDER BY asset_type, asset_key
                """,
                limit=10000,
                payload_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "asset_type": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by asset type: ac_line_segment, substation, joint",
                        },
                        "tile_ids": {
                            "type": "array",
                            "items": {"type": "string", "pattern": r"^tile_\d+_\d+$"},
                            "description": "Tile IDs to load (e.g. tile_0_3, tile_1_3). Omit for all.",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # risks — WARNING/ALERT only, JSONB metrics, no geometry
            # Frontend joins against cached shapes by segment_id.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="risks",
                client="dataset_api",
                query=f"""
                    SELECT segment_id, date::text AS date, risk_vector,
                           risk_level, risk_color_hex, metrics
                    FROM {_SCHEMA}.grid_risks
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    AND date::date IN {{{{ dates | sql_list }}}}
                    {{% if risk_vector %}}
                    AND risk_vector IN {{{{ risk_vector | sql_list }}}}
                    {{% endif %}}
                    ORDER BY date, risk_vector, risk_level
                """,
                limit=10000,
                payload_schema={
                    "type": "object",
                    "required": ["dates"],
                    "additionalProperties": False,
                    "properties": {
                        "dates": {
                            "type": "array",
                            # REQ-1235: `dates` feeds sql_list unguarded, and an
                            # empty list is a 400 here rather than `IN ()` there.
                            "minItems": 1,
                            "items": {
                                "type": "string",
                                "pattern": r"^\d{4}-\d{2}-\d{2}$",
                            },
                            "description": "ISO dates to fetch risks for (YYYY-MM-DD)",
                        },
                        "risk_vector": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["wind", "heat"]},
                            "description": "Vectors to include; omit for all",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # risks_now — nowcasting: current observations, no date filter
            # Same schema as risks but from the nowcasting table.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="risks_now",
                client="dataset_api",
                query=f"""
                    SELECT segment_id, date::text AS date, risk_vector,
                           risk_level, risk_color_hex, metrics
                    FROM {_SCHEMA}.grid_risks_now
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    {{% if risk_vector %}}
                    AND risk_vector IN {{{{ risk_vector | sql_list }}}}
                    {{% endif %}}
                    ORDER BY date, risk_vector, risk_level
                """,
                limit=10000,
                payload_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "risk_vector": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["wind", "heat"]},
                            "description": "Vectors to include; omit for all",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # risk_km — length-weighted exposure per tratta / line / operational unit
            # Grain chosen by `level`; aggregated grains recompute the index from
            # the summed km. Powers the tabular view, CSV export and DSO reports.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="risk_km",
                client="dataset_api",
                query=_RISK_KM_QUERY,
                limit=20000,
                payload_schema={
                    "type": "object",
                    "required": ["dates"],
                    "additionalProperties": False,
                    "properties": {
                        "dates": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 7,
                            "items": {
                                "type": "string",
                                "pattern": r"^\d{4}-\d{2}-\d{2}$",
                            },
                            "description": "ISO dates (YYYY-MM-DD), at most seven",
                        },
                        "level": {
                            "type": "string",
                            "enum": ["tratta", "line", "unit"],
                            "default": "tratta",
                            "description": "Row grain: tratta (as stored), line, or operational unit",
                        },
                        "risk_vector": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["wind", "heat"]},
                            "description": "Vectors to include; omit for all",
                        },
                        "operational_unit": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Operational units to include; omit for all",
                        },
                        "line_name": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "MT lines to include; omit for all",
                        },
                        "substation_name": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Primary (HV/MV) substations to include; omit for all",
                        },
                        "min_level": {
                            "type": "string",
                            "enum": ["WARNING", "ALERT"],
                            "description": "Keep rows whose worst level is at or above this",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # tree_strike_spans — static exposure overlay at span grain
            # Same tile ids as shapes (grid_tile_grid); exposure only.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="tree_strike_spans",
                client="dataset_api",
                query=f"""
                    SELECT span_id, line_name, municipality, operational_unit,
                           parent_substation_name, feeder_id, conductor_type,
                           tier, multiplier, strike_density_km, n_strike, length_m,
                           feature_geojson
                    FROM {_SCHEMA}.grid_tree_strike_spans
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    {{% if tile_ids %}}
                    AND span_id IN (
                        SELECT span_id FROM {_SCHEMA}.grid_tree_strike_tiles
                        WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                        AND tile_id IN {{{{ tile_ids | sql_list }}}}
                    )
                    {{% endif %}}
                    ORDER BY span_id
                """,
                limit=5000,
                payload_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tile_ids": {
                            "type": "array",
                            "items": {"type": "string", "pattern": r"^tile_\d+_\d+$"},
                            "description": "Tile ids from tile_index; omit for the whole overlay",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # risks_8h — WARNING/ALERT rows per 8-hour window (intra-day view)
            # Same columns as risks plus window_start / slot; heat rows are the
            # daily level repeated on the three windows.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="risks_8h",
                client="dataset_api",
                query=f"""
                    SELECT segment_id, date::text AS date, window_start::text AS window_start,
                           slot, risk_vector, risk_level, risk_color_hex, metrics
                    FROM {_SCHEMA}.grid_risks_8h
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    AND date::date IN {{{{ dates | sql_list }}}}
                    {{% if slots %}}
                    AND slot IN {{{{ slots | sql_list }}}}
                    {{% endif %}}
                    {{% if risk_vector %}}
                    AND risk_vector IN {{{{ risk_vector | sql_list }}}}
                    {{% endif %}}
                    ORDER BY date, slot, risk_vector, risk_level
                """,
                limit=30000,
                payload_schema={
                    "type": "object",
                    "required": ["dates"],
                    "additionalProperties": False,
                    "properties": {
                        "dates": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 7,
                            "items": {
                                "type": "string",
                                "pattern": r"^\d{4}-\d{2}-\d{2}$",
                            },
                            "description": "ISO dates to fetch windows for (YYYY-MM-DD)",
                        },
                        "slots": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0, "maximum": 2},
                            "description": "8-hour windows to include (0 = 00–08, 1 = 08–16, 2 = 16–24); omit for all",
                        },
                        "risk_vector": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["wind", "heat"]},
                            "description": "Vectors to include; omit for all",
                        },
                    },
                },
            ),

            # ------------------------------------------------------------------
            # trendline — daily risk percentage per vector
            # Powers sparkline charts and day-level risk badge.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="trendline",
                client="dataset_api",
                query=f"""
                    SELECT date::text AS date, risk_vector, alert_count,
                           warning_count, total_segments, risk_ratio, day_risk_level
                    FROM {_SCHEMA}.grid_risks_trendline
                    WHERE dso_id = {{{{ entity.id | sql_quote }}}}
                    AND date::date >= :date_from::date
                      AND date::date <= :date_to::date
                    {{% if risk_vector %}}
                    AND risk_vector IN {{{{ risk_vector | sql_list }}}}
                    {{% endif %}}
                    ORDER BY date, risk_vector
                """,
                limit=500,
                payload_schema={
                    "type": "object",
                    "required": ["date_from", "date_to"],
                    "additionalProperties": False,
                    "properties": {
                        "date_from": {
                            "type": "string",
                            "pattern": r"^\d{4}-\d{2}-\d{2}$",
                        },
                        "date_to": {
                            "type": "string",
                            "pattern": r"^\d{4}-\d{2}-\d{2}$",
                        },
                        "risk_vector": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["wind", "heat"]},
                        },
                    },
                },
            ),
        ]


domain = ITGridDomain()
