from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any
from typing import Any
from pydantic import BaseModel, ConfigDict, RootModel


class GenericPayload(RootModel[dict[str, Any]]):
    model_config = ConfigDict(title="GenericPayload")


class ValueDescriptorSchema(BaseModel):
    id: str = Field(..., description="Fetcher ID (domain-scoped).")
    title: str | None = None
    description: str | None = None
    kind: str | None = Field(
        None, description="Optional kind/category (e.g. timeseries, scalar)."
    )
    meta: GenericPayload


class SimulationDescriptorSchema(BaseModel):
    key: str = Field(..., description="Simulation key.")
    title: str | None = None
    description: str | None = None
    meta: GenericPayload


class ValuesRequestSchema(BaseModel):
    payload: GenericPayload


class ValueResponseSchema(BaseModel):
    payload: GenericPayload


class DescribeResponseSchema(BaseModel):
    payload: GenericPayload


class SummaryResponseSchema(BaseModel):
    payload: GenericPayload
