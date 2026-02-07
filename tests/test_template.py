# tests/test_template.py
"""
Unit tests for the Jinja2 query template engine.
"""
import pytest

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.template import render_query


class TestRenderQuery:
    def test_entity_injection(self):
        tpl = "SELECT * FROM t WHERE community_id = '{{ entity.id }}'"
        entity = EntityInfo(id="rec-1", domain_name="test")
        result = render_query(tpl, entity=entity)
        assert "rec-1" in result

    def test_bind_param_substitution(self):
        tpl = "SELECT * FROM t WHERE ts >= :start AND ts < :end"
        result = render_query(tpl, params={"start": "2024-01-01", "end": "2024-12-31"})
        assert "'2024-01-01'" in result
        assert "'2024-12-31'" in result

    def test_mixed_jinja_and_bind(self):
        tpl = (
            "SELECT * FROM t "
            "WHERE community_id = '{{ entity.id }}' "
            "AND ts >= :start"
        )
        entity = EntityInfo(id="abc", domain_name="test")
        result = render_query(tpl, entity=entity, params={"start": "2024-06-01"})
        assert "abc" in result
        assert "'2024-06-01'" in result

    def test_conditional_jinja_block(self):
        tpl = (
            "SELECT * FROM t WHERE 1=1"
            "{% if entity and entity.metadata.boundary %}"
            " AND participant_id IN {{ entity.metadata.boundary | sql_list }}"
            "{% endif %}"
        )
        # Without boundary
        entity_no_boundary = EntityInfo(id="x", domain_name="test")
        result1 = render_query(tpl, entity=entity_no_boundary)
        assert "participant_id" not in result1

        # With boundary
        entity_with = EntityInfo(
            id="x", domain_name="test", metadata={"boundary": ["p1", "p2"]}
        )
        result2 = render_query(tpl, entity=entity_with)
        assert "('p1', 'p2')" in result2

    def test_missing_bind_param_raises(self):
        tpl = "SELECT * FROM t WHERE ts >= :start"
        with pytest.raises(ValueError, match="start"):
            render_query(tpl, params={})

    def test_numeric_quoting(self):
        tpl = "SELECT * FROM t WHERE val > :threshold"
        result = render_query(tpl, params={"threshold": 42.5})
        assert "42.5" in result

    def test_none_quoting(self):
        tpl = "SELECT * FROM t WHERE val = :maybe_null"
        result = render_query(tpl, params={"maybe_null": None})
        assert "NULL" in result

    def test_no_entity(self):
        tpl = "SELECT 1"
        result = render_query(tpl)
        assert result == "SELECT 1"

    def test_sql_quote_filter(self):
        tpl = "SELECT * FROM t WHERE name = {{ name | sql_quote }}"
        result = render_query(tpl, params={"name": "O'Brien"})
        assert "'O''Brien'" in result
