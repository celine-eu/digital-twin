from __future__ import annotations
from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Generic,
    Protocol,
    Type,
    TypeVar,
    Mapping,
    runtime_checkable,
)

from celine.dt.contracts.mapper import InputMapper, OutputMapper

C = TypeVar("C")
O = TypeVar("O")


@runtime_checkable
class DTApp(Protocol[C, O]):
    """
    Digital Twin application contract.
    """

    config_type: Type[C]
    result_type: Type[O]

    input_mapper: InputMapper
    output_mapper: OutputMapper

    key: ClassVar[str]
    version: ClassVar[str] 
    defaults: ClassVar[dict[str, Any]] = {}

    async def run(self, config: C, context: Any) -> O: ...


