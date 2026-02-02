# celine/dt/core/values/coercion.py
"""
Type coercion for query string parameters based on JSON Schema.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CoercionError(ValueError):
    """Raised when a value cannot be coerced to the expected type."""

    def __init__(self, param: str, value: str, expected_type: str, reason: str = ""):
        self.param = param
        self.value = value
        self.expected_type = expected_type
        msg = f"Cannot coerce parameter '{param}' value '{value}' to {expected_type}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


def coerce_value(value: str, schema: dict[str, Any]) -> Any:
    """
    Coerce a string value to the type specified in the JSON Schema.

    Supports:
        - string: returned as-is
        - integer: parsed as int
        - number: parsed as float
        - boolean: 'true'/'1' -> True, 'false'/'0' -> False
        - array: comma-separated values, items coerced recursively
        - null: 'null'/'' -> None

    Args:
        value: String value from query parameter
        schema: JSON Schema dict with 'type' field

    Returns:
        Coerced value

    Raises:
        CoercionError: If coercion fails
    """
    schema_type = schema.get("type", "string")

    # Handle nullable types (type can be array like ["string", "null"])
    if isinstance(schema_type, list):
        # Try null first if value looks null
        if value in ("", "null") and "null" in schema_type:
            return None
        # Use first non-null type
        for t in schema_type:
            if t != "null":
                schema_type = t
                break

    if schema_type == "string":
        return value

    elif schema_type == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise CoercionError("", value, "integer", str(exc)) from exc

    elif schema_type == "number":
        try:
            return float(value)
        except ValueError as exc:
            raise CoercionError("", value, "number", str(exc)) from exc

    elif schema_type == "boolean":
        lower = value.lower()
        if lower in ("true", "1", "yes"):
            return True
        elif lower in ("false", "0", "no"):
            return False
        else:
            raise CoercionError("", value, "boolean", f"expected true/false, got '{value}'")

    elif schema_type == "null":
        if value in ("", "null"):
            return None
        raise CoercionError("", value, "null", f"expected empty or 'null', got '{value}'")

    elif schema_type == "array":
        items_schema = schema.get("items", {"type": "string"})
        parts = value.split(",") if value else []
        return [coerce_value(p.strip(), items_schema) for p in parts]

    else:
        # Unknown type, return as string
        logger.warning("Unknown schema type '%s', returning value as string", schema_type)
        return value


def coerce_params(
    params: dict[str, str],
    payload_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Coerce query string parameters based on JSON Schema.

    Also applies defaults from the schema for missing parameters.

    Args:
        params: Dict of parameter name -> string value (from query string)
        payload_schema: JSON Schema for the payload (may be None)

    Returns:
        Dict of parameter name -> coerced value

    Raises:
        CoercionError: If any coercion fails
        ValueError: If required parameter is missing
    """
    if payload_schema is None:
        # No schema, return params as-is (all strings)
        return dict(params)

    properties = payload_schema.get("properties", {})
    required = set(payload_schema.get("required", []))
    additional_allowed = payload_schema.get("additionalProperties", True)

    result: dict[str, Any] = {}

    # Process defined properties
    for prop_name, prop_schema in properties.items():
        if prop_name in params:
            try:
                result[prop_name] = coerce_value(params[prop_name], prop_schema)
            except CoercionError as exc:
                exc.param = prop_name
                raise
        elif "default" in prop_schema:
            result[prop_name] = prop_schema["default"]
        elif prop_name in required:
            raise ValueError(f"Missing required parameter: '{prop_name}'")

    # Handle additional properties not in schema
    for key, value in params.items():
        if key not in properties:
            if additional_allowed:
                result[key] = value  # Keep as string
            # If additionalProperties is False, we silently ignore

    return result
