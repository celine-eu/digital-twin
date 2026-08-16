# tests/test_template.py
"""
Unit tests for the Jinja2 query template engine.
"""
import pytest

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.template import render_query


class TestRenderQuery:
    # @verifies REQ-1201
    def test_entity_injection(self):
        tpl = "SELECT * FROM t WHERE community_id = '{{ entity.id }}'"
        entity = EntityInfo(id="rec-1", domain_name="test")
        result = render_query(tpl, entity=entity)
        assert "rec-1" in result

    # @verifies REQ-1210
    def test_bind_param_substitution(self):
        tpl = "SELECT * FROM t WHERE ts >= :start AND ts < :end"
        result = render_query(tpl, params={"start": "2024-01-01", "end": "2024-12-31"})
        assert "'2024-01-01'" in result
        assert "'2024-12-31'" in result

    # @verifies REQ-1200
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

    # @verifies REQ-1201
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

    # @verifies REQ-1242
    def test_missing_bind_param_raises(self):
        tpl = "SELECT * FROM t WHERE ts >= :start"
        with pytest.raises(ValueError, match="start"):
            render_query(tpl, params={})

    # @verifies REQ-1232
    def test_numeric_quoting(self):
        tpl = "SELECT * FROM t WHERE val > :threshold"
        result = render_query(tpl, params={"threshold": 42.5})
        assert "42.5" in result

    # @verifies REQ-1232
    def test_none_quoting(self):
        tpl = "SELECT * FROM t WHERE val = :maybe_null"
        result = render_query(tpl, params={"maybe_null": None})
        assert "NULL" in result

    def test_no_entity(self):
        tpl = "SELECT 1"
        result = render_query(tpl)
        assert result == "SELECT 1"

    # @verifies REQ-1232
    def test_sql_quote_filter(self):
        tpl = "SELECT * FROM t WHERE name = {{ name | sql_quote }}"
        result = render_query(tpl, params={"name": "O'Brien"})
        assert "'O''Brien'" in result


class TestPostgresCasts:
    """`::cast` must survive the bind-parameter pass.

    The bind-parameter regex is `(?<!:):(\\w+)`. Its negative lookbehind is the only
    thing that stops `::date` from being read as a parameter named `date`. That is
    the case which looks exactly like the thing it must not match, so it is the
    regression to hold: rewrite the regex without the lookbehind and every cast in
    every domain breaks at once, surfacing as an unrelated-looking bind error.

    See `.agents/knowledge/query-templates-are-two-phase.md`.
    """

    # @verifies REQ-1220
    def test_bare_cast_is_not_a_bind_param(self):
        tpl = "SELECT ts::date FROM t"
        assert render_query(tpl, params={}) == "SELECT ts::date FROM t"

    # @verifies REQ-1221
    def test_cast_names_that_collide_with_a_supplied_param(self):
        """The worst case: a cast whose name is also a real parameter.

        Without the lookbehind `::date` would substitute and produce `ts:'2026-01-01'`
        — still valid-looking text, and wrong.
        """
        tpl = "SELECT ts::date FROM t WHERE ts >= :date"
        result = render_query(tpl, params={"date": "2026-01-01"})
        assert "ts::date" in result
        assert ">= '2026-01-01'" in result

    # @verifies REQ-1221
    def test_bind_param_immediately_followed_by_a_cast(self):
        tpl = "SELECT * FROM t WHERE ts >= :date_from::timestamp"
        result = render_query(tpl, params={"date_from": "2026-01-01"})
        assert result == "SELECT * FROM t WHERE ts >= '2026-01-01'::timestamp"

    # @verifies REQ-1220
    def test_several_casts(self):
        tpl = "SELECT a::text, b::numeric, CAST(c AS date) FROM t"
        assert render_query(tpl, params={}) == tpl

    # @verifies REQ-1220
    def test_cast_does_not_need_the_param_to_exist(self):
        """A missing bind parameter raises. If a cast were read as one, this would
        raise too — so this asserts the cast never enters the lookup at all."""
        render_query("SELECT ts::interval FROM t", params={})


class TestInjectionBoundary:
    """Caller-supplied scalars go through bind parameters, which quote them.

    The rule these hold is the one in the knowledge entry: a caller value reaching
    the Jinja phase would become query *structure*.
    """

    # @verifies REQ-1210
    def test_bind_param_escapes_quotes(self):
        tpl = "SELECT * FROM t WHERE name = :name"
        result = render_query(tpl, params={"name": "x'; DROP TABLE t; --"})
        assert "''" in result
        assert result.count("'") % 2 == 0

    # @verifies REQ-1212
    def test_bind_param_value_is_not_re_rendered_as_jinja(self):
        """A value containing Jinja syntax is inert: substitution happens after
        rendering, so phase one never sees it."""
        tpl = "SELECT * FROM t WHERE name = :name"
        result = render_query(tpl, params={"name": "{{ entity.id }}"})
        assert "{{ entity.id }}" in result

    # @verifies REQ-1212
    def test_bind_param_value_containing_a_colon_is_not_rescanned(self):
        tpl = "SELECT * FROM t WHERE a = :a AND b = :b"
        result = render_query(tpl, params={"a": ":b", "b": "real"})
        assert "':b'" in result
        assert "'real'" in result

    # @verifies REQ-1232
    def test_boolean_is_not_quoted(self):
        result = render_query("SELECT * FROM t WHERE ok = :ok", params={"ok": True})
        assert "TRUE" in result


class TestSqlListFilter:
    # @verifies REQ-1230
    def test_numbers_are_not_quoted(self):
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        assert "(1, 2, 3)" in render_query(tpl, params={"ids": [1, 2, 3]})

    # @verifies REQ-1230
    def test_strings_are_quoted(self):
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        assert "('a', 'b')" in render_query(tpl, params={"ids": ["a", "b"]})

    # @verifies REQ-1231
    def test_non_list_raises(self):
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        with pytest.raises(TypeError, match="sql_list expects a list"):
            render_query(tpl, params={"ids": "not-a-list"})

    # @verifies REQ-1230
    def test_empty_list_renders_empty_parens(self):
        """`IN ()` is not valid SQL in PostgreSQL.

        Recorded rather than asserted-as-good: the filter has no opinion about the
        empty case, so guarding it is the template author's job — typically an
        enclosing `{% if ids %}`.
        """
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        assert "IN ()" in render_query(tpl, params={"ids": []})


class TestUndefined:
    # @verifies REQ-1241
    def test_undefined_entity_attribute_raises(self):
        tpl = "SELECT * FROM t WHERE z = '{{ entity.metadata.missing }}'"
        entity = EntityInfo(id="x", domain_name="test")
        with pytest.raises(ValueError, match="Query template error"):
            render_query(tpl, entity=entity)

    # @verifies REQ-1240
    def test_undefined_is_falsy_in_a_conditional(self):
        """Truthiness must not raise, or every `{% if entity.metadata.x %}` guard
        would fail instead of taking the else branch."""
        tpl = "SELECT 1{% if entity.metadata.missing %} AND 2{% endif %}"
        entity = EntityInfo(id="x", domain_name="test")
        assert render_query(tpl, entity=entity) == "SELECT 1"

    # @verifies REQ-1240
    def test_entity_none_is_falsy(self):
        tpl = "SELECT 1{% if entity %} AND 2{% endif %}"
        assert render_query(tpl, entity=None) == "SELECT 1"

    # @verifies REQ-1202
    def test_syntax_error_is_a_value_error(self):
        with pytest.raises(ValueError, match="Query template error"):
            render_query("SELECT {% if %}", params={})
