# tests/core/values/test_coercion.py
from __future__ import annotations

import pytest

from celine.dt.core.values.coercion import coerce_value, coerce_params, CoercionError


class TestCoerceValue:
    def test_string_passthrough(self):
        assert coerce_value("hello", {"type": "string"}) == "hello"

    def test_integer(self):
        assert coerce_value("42", {"type": "integer"}) == 42
        assert coerce_value("-10", {"type": "integer"}) == -10

    def test_integer_invalid(self):
        with pytest.raises(CoercionError):
            coerce_value("not_a_number", {"type": "integer"})

    def test_number(self):
        assert coerce_value("3.14", {"type": "number"}) == 3.14
        assert coerce_value("42", {"type": "number"}) == 42.0

    def test_number_invalid(self):
        with pytest.raises(CoercionError):
            coerce_value("not_a_number", {"type": "number"})

    def test_boolean_true(self):
        assert coerce_value("true", {"type": "boolean"}) is True
        assert coerce_value("True", {"type": "boolean"}) is True
        assert coerce_value("TRUE", {"type": "boolean"}) is True
        assert coerce_value("1", {"type": "boolean"}) is True
        assert coerce_value("yes", {"type": "boolean"}) is True

    def test_boolean_false(self):
        assert coerce_value("false", {"type": "boolean"}) is False
        assert coerce_value("False", {"type": "boolean"}) is False
        assert coerce_value("0", {"type": "boolean"}) is False
        assert coerce_value("no", {"type": "boolean"}) is False

    def test_boolean_invalid(self):
        with pytest.raises(CoercionError):
            coerce_value("maybe", {"type": "boolean"})

    def test_null(self):
        assert coerce_value("", {"type": "null"}) is None
        assert coerce_value("null", {"type": "null"}) is None

    def test_null_invalid(self):
        with pytest.raises(CoercionError):
            coerce_value("not_null", {"type": "null"})

    def test_array_of_strings(self):
        result = coerce_value("a,b,c", {"type": "array", "items": {"type": "string"}})
        assert result == ["a", "b", "c"]

    def test_array_of_integers(self):
        result = coerce_value("1,2,3", {"type": "array", "items": {"type": "integer"}})
        assert result == [1, 2, 3]

    def test_array_empty(self):
        result = coerce_value("", {"type": "array", "items": {"type": "string"}})
        assert result == []

    def test_array_trims_whitespace(self):
        result = coerce_value("a, b , c", {"type": "array", "items": {"type": "string"}})
        assert result == ["a", "b", "c"]

    def test_nullable_type_with_null_value(self):
        schema = {"type": ["string", "null"]}
        assert coerce_value("", schema) is None
        assert coerce_value("null", schema) is None

    def test_nullable_type_with_value(self):
        schema = {"type": ["string", "null"]}
        assert coerce_value("hello", schema) == "hello"

    def test_unknown_type_returns_string(self):
        assert coerce_value("value", {"type": "unknown"}) == "value"

    def test_default_type_is_string(self):
        assert coerce_value("value", {}) == "value"


class TestCoerceParams:
    def test_coerce_with_schema(self):
        params = {"count": "10", "name": "test"}
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "name": {"type": "string"},
            },
        }

        result = coerce_params(params, schema)

        assert result == {"count": 10, "name": "test"}

    def test_apply_defaults(self):
        params = {"required_field": "value"}
        schema = {
            "type": "object",
            "properties": {
                "required_field": {"type": "string"},
                "optional_field": {"type": "string", "default": "default_value"},
            },
        }

        result = coerce_params(params, schema)

        assert result["required_field"] == "value"
        assert result["optional_field"] == "default_value"

    def test_missing_required_raises(self):
        params = {}
        schema = {
            "type": "object",
            "required": ["must_have"],
            "properties": {
                "must_have": {"type": "string"},
            },
        }

        with pytest.raises(ValueError, match="Missing required"):
            coerce_params(params, schema)

    def test_additional_properties_allowed(self):
        params = {"known": "1", "unknown": "extra"}
        schema = {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "known": {"type": "integer"},
            },
        }

        result = coerce_params(params, schema)

        assert result["known"] == 1
        assert result["unknown"] == "extra"  # kept as string

    def test_additional_properties_ignored(self):
        params = {"known": "1", "unknown": "extra"}
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "known": {"type": "integer"},
            },
        }

        result = coerce_params(params, schema)

        assert result == {"known": 1}  # unknown is dropped

    def test_no_schema_returns_strings(self):
        params = {"a": "1", "b": "2"}
        result = coerce_params(params, None)
        assert result == {"a": "1", "b": "2"}

    def test_coercion_error_includes_param_name(self):
        params = {"bad_int": "not_a_number"}
        schema = {
            "type": "object",
            "properties": {
                "bad_int": {"type": "integer"},
            },
        }

        with pytest.raises(CoercionError) as exc_info:
            coerce_params(params, schema)

        assert exc_info.value.param == "bad_int"
