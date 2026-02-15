# celine/dt/core/values/executor.py
"""
Value fetch execution engine.

Handles payload validation, Jinja-based query rendering with entity
context injection, client query execution, and optional output mapping.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import jsonschema

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.values.template import render_query

if TYPE_CHECKING:
    from celine.dt.api.context import Ctx


logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when payload validation against JSON Schema fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_error",
            "message": self.message,
            "errors": self.errors,
        }

    def __str__(self) -> str:
        return self.message


@dataclass
class FetchResult:
    """Result of a value fetch operation."""

    items: list[dict[str, Any]]
    limit: int
    offset: int
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "limit": self.limit,
            "offset": self.offset,
            "count": self.count,
        }


@dataclass
class FetcherDescriptor:
    """Resolved fetcher: spec + live client + optional mapper."""

    spec: ValueFetcherSpec
    client: Any
    output_mapper: Any | None = None

    @property
    def id(self) -> str:
        return self.spec.id


class ValuesFetcher:
    """Stateless executor for value fetch operations."""

    def validate_payload(
        self,
        payload: dict[str, Any],
        descriptor: FetcherDescriptor,
    ) -> dict[str, Any]:
        schema = descriptor.spec.payload_schema
        if schema is None:
            return payload

        # Apply defaults
        properties = schema.get("properties", {})
        enriched = dict(payload)
        for prop_name, prop_schema in properties.items():
            if prop_name not in enriched and "default" in prop_schema:
                enriched[prop_name] = prop_schema["default"]

        try:
            jsonschema.validate(enriched, schema)
        except jsonschema.ValidationError as exc:
            logger.warning(
                "Payload validation failed for '%s': %s", descriptor.id, exc.message
            )
            raise ValidationError(
                f"Payload validation failed: {exc.message}",
                errors=[exc.message],
            ) from exc

        return enriched

    async def fetch(
        self,
        descriptor: FetcherDescriptor,
        payload: dict[str, Any],
        *,
        entity: EntityInfo | None = None,
        limit: int | None = None,
        offset: int | None = None,
        ctx: Ctx | None,
    ) -> FetchResult:
        """Execute a value fetch with Jinja template rendering.

        Args:
            descriptor: Resolved fetcher descriptor.
            payload: User-supplied parameters.
            entity: Entity context for Jinja templates.
            limit: Override default limit.
            offset: Override default offset.

        Returns:
            ``FetchResult`` with items and pagination metadata.
        """
        spec = descriptor.spec
        effective_limit = limit if limit is not None else spec.limit
        effective_offset = offset if offset is not None else spec.offset

        validated = self.validate_payload(payload, descriptor)

        # Render query with Jinja + bind params
        query: str | None = None
        if spec.query:
            try:
                query = render_query(spec.query, entity=entity, params=validated)
            except ValueError:
                logger.exception("Query rendering failed for fetcher '%s'", spec.id)
                raise

        logger.debug(
            "Fetcher '%s': query=%s limit=%d offset=%d",
            spec.id,
            (query[:80] + "...") if query and len(query) > 80 else query,
            effective_limit,
            effective_offset,
        )

        try:
            items = await descriptor.client.query(
                sql=query or "",
                limit=effective_limit,
                offset=effective_offset,
                ctx=ctx,
            )
        except Exception:
            logger.error("Client query failed for fetcher '%s'", spec.id)
            raise

        if descriptor.output_mapper:
            try:
                items = [descriptor.output_mapper.map(item) for item in items]
            except Exception:
                logger.exception("Output mapping failed for fetcher '%s'", spec.id)
                raise

        return FetchResult(
            items=items,
            limit=effective_limit,
            offset=effective_offset,
            count=len(items),
        )
