# celine/dt/domains/grid/domain.py
"""
Grid resilience domain — weather-driven risk monitoring for MT distribution networks.

Route surface::

    /grid/{network_id}/wind/map             (legacy — kept for backwards compat)
    /grid/{network_id}/wind/bosco
    /grid/{network_id}/wind/alert-distribution
    /grid/{network_id}/wind/trend
    /grid/{network_id}/heat/map             (legacy — kept for backwards compat)
    /grid/{network_id}/heat/alert-distribution
    /grid/{network_id}/heat/trend
    /grid/{network_id}/substations/map

Value fetchers (auto-generated /values/{id} GET + POST)::

    it-grid.filters     — distinct topology values + network extent (single aggregation row)
    it-grid.shapes      — static CIM asset topology, loaded once by frontend
    it-grid.risks       — WARNING/ALERT risk rows by date, no geometry
    it-grid.trendline   — daily risk percentage indicator per vector
"""
from __future__ import annotations

import logging
from typing import ClassVar

from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.clients.dataset_api import DatasetSqlApiClient

logger = logging.getLogger(__name__)

_SCHEMA = "ds_dev_gold"


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
                """,
                limit=1,
            ),

            # ------------------------------------------------------------------
            # shapes — static CIM asset topology, geometry only
            # Frontend loads once and caches; re-fetches only on topology change.
            # ------------------------------------------------------------------
            ValueFetcherSpec(
                id="shapes",
                client="dataset_api",
                query=f"""
                    SELECT segment_id, asset_type, asset_key, conductor_type,
                           parent_substation_name, operational_unit, municipality,
                           feeder_id, length_m, is_vegetated_zone,
                           voltage_class, label, label_id,
                           feature_geojson
                    FROM {_SCHEMA}.grid_shapes
                    {{% if asset_type %}}
                    WHERE asset_type IN ({{{{ asset_type | sql_list }}}})
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
                            "description": "Filter by asset type: ac_line_segment, substation",
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
                    WHERE date::date IN ({{{{ dates | sql_list }}}})
                    {{% if risk_vector %}}
                    AND risk_vector IN ({{{{ risk_vector | sql_list }}}})
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
                    WHERE date::date >= :date_from::date
                      AND date::date <= :date_to::date
                    {{% if risk_vector %}}
                    AND risk_vector IN ({{{{ risk_vector | sql_list }}}})
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
