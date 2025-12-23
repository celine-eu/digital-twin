from __future__ import annotations
from typing import Protocol, TypeVar, runtime_checkable, Mapping

I = TypeVar("I", covariant=True)
O = TypeVar("O", contravariant=True)


@runtime_checkable
class InputMapper(Protocol[I]):
    def map(self, raw: Mapping) -> I: ...


@runtime_checkable
class OutputMapper(Protocol[O]):
    def map(self, obj: O) -> object: ...
