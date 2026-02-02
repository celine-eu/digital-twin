from __future__ import annotations
from typing import Protocol, Type, TypeVar, runtime_checkable, Mapping

I = TypeVar("I")
O = TypeVar("O")


@runtime_checkable
class InputMapper(Protocol[I]):
    input_type: Type[I]

    def map(self, raw: Mapping) -> I: ...


@runtime_checkable
class OutputMapper(Protocol[O]):
    output_type: Type[O]

    def map(self, result: O) -> object: ...
