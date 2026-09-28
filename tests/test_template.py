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

    # @verifies REQ-1215
    def test_a_colon_name_inside_a_rendered_list_element_is_not_substituted(self):
        """sql_list renders caller text as literals before phase 2 runs; a `:ids` in
        one element must stay text, or the substituted quotes close the literal."""
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }} AND s = :source"
        ids = ["x:ids", ") OR TRUE UNION SELECT 1 --"]
        result = render_query(tpl, params={"ids": ids, "source": "src"})
        assert result == (
            "SELECT * FROM t WHERE id IN ('x:ids', ') OR TRUE UNION SELECT 1 --')"
            " AND s = 'src'"
        )

    # @verifies REQ-1215
    def test_a_colon_name_after_a_doubled_quote_stays_inside_the_literal(self):
        tpl = "SELECT * FROM t WHERE a = {{ v | sql_quote }} AND b = :b"
        result = render_query(tpl, params={"v": "it's :b", "b": 1})
        assert result == "SELECT * FROM t WHERE a = 'it''s :b' AND b = 1"

    # @verifies REQ-1215
    def test_a_colon_name_in_a_template_literal_or_identifier_is_text(self):
        tpl = "SELECT \"a:b\" FROM t WHERE ts = '2024-01-01 00:00:00' AND x = :x"
        result = render_query(tpl, params={"x": 2})
        assert result == "SELECT \"a:b\" FROM t WHERE ts = '2024-01-01 00:00:00' AND x = 2"

    # @verifies REQ-1215
    def test_bind_params_around_literals_are_still_substituted(self):
        tpl = "SELECT * FROM t WHERE a = :a AND k = '' AND b = :b::text"
        result = render_query(tpl, params={"a": "p", "b": "q"})
        assert result == "SELECT * FROM t WHERE a = 'p' AND k = '' AND b = 'q'::text"

    # @verifies REQ-1215
    def test_an_unterminated_quote_fails(self):
        with pytest.raises(ValueError, match="Unterminated"):
            render_query("SELECT * FROM t WHERE a = 'x AND b = :b", params={"b": 1})

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

    # @verifies REQ-1234
    def test_empty_list_is_refused(self):
        """`IN ()` is not valid SQL in PostgreSQL, so the filter refuses to render it.

        What an empty list means is the template's decision, typically an enclosing
        `{% if ids %}` (REQ-1235); the filter only makes forgetting it loud here
        rather than a dataset-api 400 surfacing as a 500.
        """
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        with pytest.raises(ValueError, match="sql_list"):
            render_query(tpl, params={"ids": []})

    # @verifies REQ-1234
    def test_empty_tuple_is_refused(self):
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        with pytest.raises(ValueError, match="sql_list"):
            render_query(tpl, params={"ids": ()})

    # @verifies REQ-1234
    def test_guarded_empty_list_renders_the_else_branch(self):
        tpl = (
            "SELECT * FROM t WHERE {% if ids %}id IN {{ ids | sql_list }}"
            "{% else %}FALSE{% endif %}"
        )
        assert render_query(tpl, params={"ids": []}) == "SELECT * FROM t WHERE FALSE"

    # @verifies REQ-1233
    def test_embedded_quote_is_doubled(self):
        """An element containing `'` must not end the literal early."""
        tpl = "SELECT * FROM t WHERE id IN {{ ids | sql_list }}"
        result = render_query(tpl, params={"ids": ["a", "x') OR ('1'='1"]})
        assert result == "SELECT * FROM t WHERE id IN ('a', 'x'') OR (''1''=''1')"

    # @verifies REQ-1233
    def test_elements_render_as_sql_quote_renders_them(self):
        from celine.dt.core.values.template import _sql_list_filter, _sql_quote_filter

        values = ["O'Brien", 3, 2.5, True, None, "plain"]
        expected = "(" + ", ".join(_sql_quote_filter(v) for v in values) + ")"
        assert _sql_list_filter(values) == expected
        assert expected == "('O''Brien', 3, 2.5, TRUE, NULL, 'plain')"


    # @verifies REQ-1236
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numbers_are_rejected(self, bad):
        from celine.dt.core.values.template import _sql_list_filter, _sql_quote_filter

        with pytest.raises(ValueError, match="non-finite"):
            _sql_quote_filter(bad)
        with pytest.raises(ValueError, match="non-finite"):
            _sql_list_filter([1.0, bad])
        with pytest.raises(ValueError, match="non-finite"):
            render_query("SELECT :x", params={"x": bad})

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
