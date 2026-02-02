# celine/dt/contracts/app.py
"""
DTApp contract for external-facing operations.

Apps are the entry points of the Digital Twin, exposed via the /apps API.
They orchestrate components and may have side effects (events, state).

Design intent:
- Components are pure compute building blocks (internal).
- Apps are orchestration / exposure units (external).
- Simulations are exploration units (external, scenario + parameters + runs).

This contract intentionally keeps mappers lightweight and *payload-only*:
the DT runtime provides a RunContext to the app itself; mappers are only
responsible for translating payload/result shapes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Mapping,
    Optional,
    Protocol,
    Type,
    TypeVar,
    runtime_checkable,
)

from pydantic import BaseModel, Field

from celine.dt.contracts.mapper import InputMapper, OutputMapper

C = TypeVar("C", bound=BaseModel)  # Config type
O = TypeVar("O", bound=BaseModel)  # Output/Result type


@runtime_checkable
class DTApp(Protocol[C, O]):
    """Digital Twin App contract."""

    key: ClassVar[str]
    version: ClassVar[str]

    config_type: Type[C]
    result_type: Type[O]

    # Optional adapters for API payload/result shapes (JSON-LD, ontology mapping, etc.)
    input_mapper: Optional[InputMapper[C]]
    output_mapper: Optional[OutputMapper[O]]

    async def run(self, config: C, context: Any) -> O: ...


@dataclass
class AppDescriptor:
    """Descriptor wrapping an app plus defaults and schema helpers."""

    def __init__(self, app: DTApp, defaults: Mapping[str, Any] | None = None) -> None:
        self.app = app
        self.defaults = defaults or {}

    app: DTApp[Any, Any]
    defaults: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.app.key

    @property
    def version(self) -> str:
        return self.app.version

    @property
    def config_schema(self) -> dict[str, Any]:
        return self.app.config_type.model_json_schema()

    @property
    def result_schema(self) -> dict[str, Any]:
        return self.app.result_type.model_json_schema()

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "defaults": dict(self.defaults),
            "config_schema": self.config_schema,
            "result_schema": self.result_schema,
        }


class AppRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
