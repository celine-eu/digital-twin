# celine/dt/core/values/executor.py
"""
Execution logic for value fetchers.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import jsonschema

from celine.dt.core.values.registry import FetcherDescriptor

logger = logging.getLogger(__name__)

# Pattern for named parameters in queries: :param_name
PARAM_PATTERN = re.compile(r":(\w+)")


@dataclass
class FetchResult:
    """
    Result from a value fetch operation.

    Matches Dataset API response format for consistency.

    Attributes:
        items: List of result records
        limit: Limit used in query
        offset: Offset used in query
        count: Number of items returned
    """

    items: list[dict[str, Any]]
    limit: int
    offset: int
    count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON response."""
        return {
            "items": self.items,
            "limit": self.limit,
            "offset": self.offset,
            "count": self.count,
        }


class ValidationError(ValueError):
    """Raised when payload validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(message)


class ValuesFetcher:
    """
    Executes value fetch operations.

    Handles:
        - Payload validation against JSON Schema
        - Query parameter substitution
        - Client query execution
        - Output mapping (if configured)
    """

    def validate_payload(
        self,
        payload: dict[str, Any],
        descriptor: FetcherDescriptor,
    ) -> dict[str, Any]:
        """
        Validate payload against fetcher's JSON Schema.

        Also applies defaults from schema.

        Args:
            payload: Input parameters
            descriptor: Fetcher descriptor with schema

        Returns:
            Validated payload with defaults applied

        Raises:
            ValidationError: If validation fails
        """
        schema = descriptor.spec.payload_schema

        if schema is None:
            # No schema defined, accept any payload
            return payload

        # Apply defaults from schema
        properties = schema.get("properties", {})
        payload_with_defaults = dict(payload)

        for prop_name, prop_schema in properties.items():
            if prop_name not in payload_with_defaults and "default" in prop_schema:
                payload_with_defaults[prop_name] = prop_schema["default"]

        # Validate against schema
        try:
            jsonschema.validate(payload_with_defaults, schema)
        except jsonschema.ValidationError as exc:
            logger.warning(
                "Payload validation failed for fetcher '%s': %s",
                descriptor.id,
                exc.message,
            )
            raise ValidationError(
                f"Payload validation failed: {exc.message}",
                errors=[exc.message],
            ) from exc

        return payload_with_defaults

    def build_query(
        self,
        query_template: Any,
        params: dict[str, Any],
    ) -> str:
        """
        Build query by substituting named parameters.

        Parameters use :param_name syntax. Values are quoted appropriately
        for SQL injection safety (though the Dataset API should also sanitize).

        Args:
            query_template: Query template with :param placeholders
            params: Parameter name -> value mapping

        Returns:
            Query with parameters substituted

        Raises:
            ValueError: If a required parameter is missing
        """
        if query_template is None:
            return ""

        if not isinstance(query_template, str):
            # Non-string query (e.g., dict for non-SQL clients)
            # Just return as-is, client handles it
            return query_template

        def replacer(match: re.Match) -> str:
            param_name = match.group(1)

            if param_name not in params:
                raise ValueError(f"Query parameter ':{param_name}' not provided")

            value = params[param_name]
            return self._quote_value(value)

        return PARAM_PATTERN.sub(replacer, query_template)

    def _quote_value(self, value: Any) -> str:
        """
        Quote a value for safe SQL inclusion.

        Note: This is defense-in-depth. The Dataset API should also sanitize.
        """
        if value is None:
            return "NULL"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape single quotes
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, (list, tuple)):
            quoted = ", ".join(self._quote_value(v) for v in value)
            return f"({quoted})"
        else:
            escaped = str(value).replace("'", "''")
            return f"'{escaped}'"

    async def fetch(
        self,
        descriptor: FetcherDescriptor,
        payload: dict[str, Any],
        limit: int | None = None,
        offset: int | None = None,
    ) -> FetchResult:
        """
        Execute a value fetch operation.

        Args:
            descriptor: Fetcher descriptor with client and config
            payload: Validated input parameters
            limit: Override default limit (optional)
            offset: Override default offset (optional)

        Returns:
            FetchResult with items and pagination info

        Raises:
            ValidationError: If payload validation fails
            ValueError: If query building fails
            Exception: If client query fails
        """
        spec = descriptor.spec

        # Use provided or default limit/offset
        effective_limit = limit if limit is not None else spec.limit
        effective_offset = offset if offset is not None else spec.offset

        # Validate payload
        validated_payload = self.validate_payload(payload, descriptor)

        # Build query
        query = self.build_query(spec.query, validated_payload)

        logger.debug(
            "Executing fetcher '%s': query='%s', limit=%d, offset=%d",
            spec.id,
            query[:100] + "..." if len(str(query)) > 100 else query,
            effective_limit,
            effective_offset,
        )

        # Execute via client
        try:
            items = await descriptor.client.query(
                sql=query,
                limit=effective_limit,
                offset=effective_offset,
            )
        except Exception as exc:
            logger.error(
                "Client query failed for fetcher '%s': %s",
                spec.id,
                exc,
            )
            raise

        # Apply output mapper if configured
        if descriptor.output_mapper:
            try:
                items = [descriptor.output_mapper.map(item) for item in items]
            except Exception as exc:
                logger.error(
                    "Output mapping failed for fetcher '%s': %s",
                    spec.id,
                    exc,
                )
                raise

        return FetchResult(
            items=items,
            limit=effective_limit,
            offset=effective_offset,
            count=len(items),
        )
