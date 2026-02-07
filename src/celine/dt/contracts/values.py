# celine/dt/contracts/values.py
"""
Value fetcher contracts.

A value fetcher is a declarative query definition that maps a client +
Jinja-templated query + JSON-Schema payload into a data retrieval
operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ValueFetcherSpec:
    """Specification for a single value fetcher.

    Attributes:
        id: Unique identifier (domain-namespaced at runtime).
        client: Name of the client from the clients registry.
        query: Jinja2 template for the query. Structural parts use
            ``{{ entity.id }}``, ``{% if ... %}``, etc. Bind parameters
            use ``:param_name`` syntax for safe value injection.
        limit: Default result limit.
        offset: Default pagination offset.
        payload_schema: Optional JSON Schema for input validation.
        output_mapper: Optional import path to an output mapper class.
    """

    id: str
    client: str
    query: str | None = None
    limit: int = 100
    offset: int = 0
    payload_schema: dict[str, Any] | None = None
    output_mapper: str | None = None


class ValuesRequest(BaseModel):
    """POST body for the values API."""

    payload: dict[str, Any] = Field(default_factory=dict)
