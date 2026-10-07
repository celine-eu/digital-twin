# tests/test_grid_domain.py
"""
The `it-grid` domain's own fetchers, rendered against a mock client.

Nothing here reaches a database: the point is what SQL the fetcher asks for given a
payload, and which payloads it refuses. The real `ITGridDomain` is loaded, so a spec
edit is what these tests see.
"""

from __future__ import annotations

import re
import types

import pytest

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.executor import (
    FetcherDescriptor,
    ValidationError,
    ValuesFetcher,
)
from celine.dt.domains.grid.domain import ITGridDomain

from tests.conftest import MockDatasetClient

# A request context carrying a caller token (REQ-1133).
CALLER = types.SimpleNamespace(token="caller-synthetic")
# The network every fetch is narrowed to.
NETWORK = EntityInfo(id="example-dso", domain_name="it-grid")


def _spec(fetcher_id: str):
    specs = {s.id: s for s in ITGridDomain().get_value_specs()}
    assert fetcher_id in specs, f"{fetcher_id} not declared: {sorted(specs)}"
    return specs[fetcher_id]


async def _render(payload: dict, fetcher_id: str = "risk_km") -> str:
    client = MockDatasetClient(rows=[])
    desc = FetcherDescriptor(spec=_spec(fetcher_id), client=client)
    await ValuesFetcher().fetch(desc, payload, entity=NETWORK, ctx=CALLER)
    assert client.last_sql is not None
    return re.sub(r"\s+", " ", client.last_sql).strip()


DATES = {"dates": ["2026-09-11"]}


# @verifies REQ-1300
def test_risk_km_is_declared_over_grid_risk_km_with_a_seven_day_limit():
    spec = _spec("risk_km")
    assert spec.client == "dataset_api"
    assert "grid_risk_km" in spec.query
    assert spec.limit >= 20000


class TestGrain:
    @pytest.mark.asyncio
    # @verifies REQ-1301
    async def test_default_level_is_tratta_rows_as_stored(self):
        sql = await _render(DATES)
        assert "GROUP BY" not in sql
        assert "segment_id" in sql
        assert "'tratta' AS level" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1301
    async def test_line_level_groups_by_line_name(self):
        sql = await _render({**DATES, "level": "line"})
        assert re.search(r"GROUP BY date, risk_vector, line_name\b", sql)
        assert "'line' AS level" in sql
        assert "segment_id" not in sql

    @pytest.mark.asyncio
    # @verifies REQ-1301
    async def test_unit_level_groups_by_operational_unit(self):
        sql = await _render({**DATES, "level": "unit"})
        assert re.search(r"GROUP BY date, risk_vector, operational_unit\b", sql)
        assert "'unit' AS level" in sql
        assert "line_name" not in sql.split("GROUP BY")[1]

    @pytest.mark.asyncio
    # @verifies REQ-1301
    async def test_aggregated_levels_recompute_the_index_from_summed_km(self):
        for level in ("line", "unit"):
            sql = await _render({**DATES, "level": level})
            assert "sum(km_alert)" in sql
            assert "nullif(sum(km_total), 0)" in sql
            assert "avg(risk_index)" not in sql


class TestFilters:
    @pytest.mark.asyncio
    # @verifies REQ-1302
    async def test_no_optional_filter_means_no_extra_clause(self):
        sql = await _render(DATES)
        assert "date::date IN ('2026-09-11')" in sql
        for col in (
            "risk_vector IN",
            "operational_unit IN",
            "line_name IN",
            "parent_substation_name IN",
            "worst_level",
        ):
            assert col not in sql.split("WHERE", 1)[1].split("ORDER BY")[0]

    @pytest.mark.asyncio
    # @verifies REQ-1302
    async def test_each_filter_lands_in_the_where_clause_when_given(self):
        sql = await _render(
            {
                **DATES,
                "risk_vector": ["wind"],
                "operational_unit": ["U1", "U2"],
                "line_name": ["TENNA"],
                "substation_name": ["VARENA"],
            }
        )
        assert "risk_vector IN ('wind')" in sql
        assert "operational_unit IN ('U1', 'U2')" in sql
        assert "line_name IN ('TENNA')" in sql
        assert "parent_substation_name IN ('VARENA')" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1302
    async def test_min_level_warning_keeps_warning_and_alert_at_tratta_grain(self):
        sql = await _render({**DATES, "min_level": "WARNING"})
        assert "worst_level IN ('ALERT', 'WARNING')" in sql
        sql = await _render({**DATES, "min_level": "ALERT"})
        assert "worst_level = 'ALERT'" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1302
    async def test_min_level_is_a_having_clause_on_aggregated_grains(self):
        sql = await _render({**DATES, "level": "unit", "min_level": "ALERT"})
        having = sql.split("HAVING", 1)[1]
        assert "bool_or(worst_level = 'ALERT')" in having
        assert "worst_level" not in sql.split("WHERE", 1)[1].split("GROUP BY")[0]


class TestValidation:
    @pytest.mark.asyncio
    # @verifies REQ-1303
    async def test_dates_are_required(self):
        with pytest.raises(ValidationError):
            await _render({"level": "unit"})

    @pytest.mark.asyncio
    # @verifies REQ-1303
    async def test_a_malformed_date_is_refused(self):
        with pytest.raises(ValidationError):
            await _render({"dates": ["11/09/2026"]})

    @pytest.mark.asyncio
    # @verifies REQ-1303
    async def test_an_unknown_level_is_refused(self):
        with pytest.raises(ValidationError):
            await _render({**DATES, "level": "feeder"})


class TestTreeStrikeSpans:
    # @verifies REQ-1304
    def test_is_declared_over_the_spans_table_with_room_for_the_whole_overlay(self):
        spec = _spec("tree_strike_spans")
        assert spec.client == "dataset_api"
        assert "grid_tree_strike_spans" in spec.query
        assert "feature_geojson" in spec.query
        assert spec.limit >= 5000

    @pytest.mark.asyncio
    # @verifies REQ-1305
    async def test_without_tile_ids_every_span_is_returned(self):
        sql = await _render({}, "tree_strike_spans")
        where = sql.split("WHERE", 1)[1].split("ORDER BY")[0]
        assert where.strip() == "dso_id = 'example-dso'"
        assert "grid_tree_strike_tiles" not in sql

    @pytest.mark.asyncio
    # @verifies REQ-1305
    async def test_tile_ids_restrict_through_the_span_tile_index(self):
        sql = await _render({"tile_ids": ["tile_1_2", "tile_3_4"]}, "tree_strike_spans")
        assert "grid_tree_strike_tiles" in sql
        assert "tile_id IN ('tile_1_2', 'tile_3_4')" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1305
    async def test_a_malformed_tile_id_is_refused(self):
        with pytest.raises(ValidationError):
            await _render({"tile_ids": ["1;drop"]}, "tree_strike_spans")


class TestShapesThermal:
    @pytest.mark.asyncio
    # @verifies REQ-1308
    async def test_shapes_selects_the_thermal_columns_and_name(self):
        sql = await _render({"asset_type": ["joint"]}, "shapes")
        # Restrict to the SELECT list: "name" alone is a substring of pre-existing
        # columns (parent_substation_name, line_name), so the check must not just
        # look for "name" anywhere in the rendered SQL.
        select_list = sql.split(" FROM ", 1)[0]
        for col in (
            "thermal_tier",
            "thermal_margin_c",
            "thermal_theta_max_c",
            "thermal_insulation",
            "is_asphalt",
            "anno_posa",
            "technology",
            "m_r_critico",
        ):
            assert col in select_list
        assert re.search(r"\bname\b", select_list), select_list

    @pytest.mark.asyncio
    # @verifies REQ-1311
    async def test_shapes_selects_the_tree_strike_km_breakdown(self):
        sql = await _render({}, "shapes")
        select_list = sql.split(" FROM ", 1)[0]
        for col in ("strike_km_high", "strike_km_mid", "strike_km_low"):
            assert col in select_list, select_list

    @pytest.mark.asyncio
    # @verifies REQ-1308
    async def test_shapes_asset_type_filter_renders_joint_in_the_where_clause(self):
        sql = await _render({"asset_type": ["joint"]}, "shapes")
        assert "asset_type IN ('joint')" in sql

    # @verifies REQ-1308
    def test_shapes_payload_description_mentions_joint(self):
        spec = _spec("shapes")
        description = spec.payload_schema["properties"]["asset_type"]["description"]
        assert "joint" in description


class TestRiskKmThermal:
    @pytest.mark.asyncio
    # @verifies REQ-1309
    async def test_tratta_selects_thermal_km_columns(self):
        sql = await _render(DATES)
        assert "km_thermal_high" in sql
        assert "km_thermal_mid" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1309
    async def test_line_level_sums_thermal_km_columns(self):
        sql = await _render({**DATES, "level": "line"})
        assert "sum(km_thermal_high)" in sql
        assert "sum(km_thermal_mid)" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1309
    async def test_unit_level_sums_thermal_km_columns(self):
        sql = await _render({**DATES, "level": "unit"})
        assert "sum(km_thermal_high)" in sql
        assert "sum(km_thermal_mid)" in sql


class TestJointRiskRows:
    """REQ-1310 is a contract note, not a fetcher change: joint rows land in the
    gold risk tables (another repo's concern) and ride the existing `metrics`
    jsonb column under `risk_vector = 'heat'`. This just pins the invariant the
    note relies on: none of the three risk fetchers gained or lost a column."""

    # @verifies REQ-1310
    def test_risks_fetchers_keep_their_opaque_metrics_column(self):
        for fetcher_id in ("risks", "risks_now", "risks_8h"):
            spec = _spec(fetcher_id)
            assert "metrics" in spec.query
            assert "risk_vector" in spec.query


class TestRisks8h:
    # @verifies REQ-1306
    def test_is_declared_over_grid_risks_8h_with_the_window_columns(self):
        spec = _spec("risks_8h")
        assert spec.client == "dataset_api"
        assert "grid_risks_8h" in spec.query
        for col in ("segment_id", "window_start", "slot", "risk_vector", "risk_level", "metrics"):
            assert col in spec.query
        assert spec.limit >= 30000

    @pytest.mark.asyncio
    # @verifies REQ-1307
    async def test_dates_are_required_and_slots_optional(self):
        with pytest.raises(ValidationError):
            await _render({}, "risks_8h")
        sql = await _render({"dates": ["2026-09-11"]}, "risks_8h")
        assert "date::date IN ('2026-09-11')" in sql
        assert "slot IN" not in sql

    @pytest.mark.asyncio
    # @verifies REQ-1307
    async def test_slots_and_vector_restrict_when_given(self):
        sql = await _render(
            {"dates": ["2026-09-11"], "slots": [1, 2], "risk_vector": ["wind"]}, "risks_8h"
        )
        assert "slot IN (1, 2)" in sql
        assert "risk_vector IN ('wind')" in sql

    @pytest.mark.asyncio
    # @verifies REQ-1307
    async def test_a_slot_outside_the_day_is_refused(self):
        with pytest.raises(ValidationError):
            await _render({"dates": ["2026-09-11"], "slots": [3]}, "risks_8h")
