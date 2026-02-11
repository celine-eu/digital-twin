from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class ValueDescriptorSchema(BaseModel):
    id: str = Field(..., description="Fetcher ID (domain-scoped).")
    title: str | None = None
    description: str | None = None
    kind: str | None = Field(
        None, description="Optional kind/category (e.g. timeseries, scalar)."
    )
    meta: dict[str, Any] = Field(default_factory=dict)


class SimulationDescriptorSchema(BaseModel):
    key: str = Field(..., description="Simulation key.")
    title: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ValuesRequestSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ValueResponseSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class DescribeResponseSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class SummaryResponseSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
