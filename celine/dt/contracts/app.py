from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, Protocol, TypeVar, Mapping, runtime_checkable

C = TypeVar("C", contravariant=True)
O = TypeVar("O", covariant=True)


@runtime_checkable
class DTApp(Protocol[C, O]):
    """
    Digital Twin application contract.
    """

    key: ClassVar[str]
    version: ClassVar[str]

    datasets: ClassVar[dict[str, str]]
    defaults: ClassVar[dict[str, Any]] = field(default_factory=dict)

    async def run(self, config: C, context: Any) -> O: ...
