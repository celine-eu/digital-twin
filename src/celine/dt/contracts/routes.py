from __future__ import annotations
from dataclasses import is_dataclass

from pydantic import BaseModel, Field
from typing import Any
from typing import Any
from pydantic import BaseModel, ConfigDict, RootModel

from celine.dt.core.values.executor import FetcherDescriptor
from celine.dt.contracts.values import ValueFetcherSpec


class GenericPayload(RootModel[dict[str, Any]]):
    model_config = ConfigDict(title="GenericPayload")


class GenericListPayload(RootModel[list[dict[str, Any]]]):
    model_config = ConfigDict(title="GenericListPayload")


class DescriptorSpecSchema(BaseModel):

    id: str = Field(..., description="Fetcher ID (domain-scoped).")
    client: str = Field(description="Fetcher client", default="dataset_api")

    query: str | None = Field(default="", description="Query")
    limit: int = Field(default=100, description="Query limit")
    offset: int = Field(default=0, description="Query offset")

    payload_schema: dict[str, Any] | None = Field(
        default_factory=dict, description="Payload schema"
    )
    output_mapper: str | None = Field(description="Payload mapper")

    @staticmethod
    def from_spec(d: ValueFetcherSpec):
        return DescriptorSpecSchema(
            id=d.id,
            client=d.client,
            limit=d.limit,
            offset=d.offset,
            payload_schema=d.payload_schema,
            output_mapper=d.output_mapper,
        )


class ValueDescriptorSchema(BaseModel):
    id: str = Field(..., description="Fetcher ID (domain-scoped).")
    spec: DescriptorSpecSchema = Field(
        ..., description="Fetcher specs (domain-scoped)."
    )

    @staticmethod
    def from_descriptor(d: FetcherDescriptor):
        return ValueDescriptorSchema(
            id=d.id, spec=DescriptorSpecSchema.from_spec(d.spec)
        )


class SimulationDescriptorSchema(BaseModel):
    key: str = Field(..., description="Simulation key.")
    title: str | None = None
    description: str | None = None
    meta: GenericPayload


class ValuesRequestSchema(BaseModel):
    payload: GenericPayload


class FetchResultSchema(BaseModel):
    """Result of a value fetch operation."""

    items: list[dict[str, Any]]
    limit: int
    offset: int
    count: int

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )

    @staticmethod
    def from_dataclass(obj: Any) -> "FetchResultSchema":
        if not is_dataclass(obj):
            raise TypeError(f"Expected dataclass, got {type(obj)!r}")

        return FetchResultSchema.model_validate(obj.__dict__)


class DescribeResponseSchema(BaseModel):
    payload: GenericPayload


class SummaryResponseSchema(BaseModel):
    payload: GenericPayload
