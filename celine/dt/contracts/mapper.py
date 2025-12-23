from __future__ import annotations
from typing import Protocol, TypeVar, runtime_checkable

I = TypeVar("I")
O = TypeVar("O")


@runtime_checkable
class InputMapper(Protocol[I]):
    def map(self, raw: dict) -> I: ...


@runtime_checkable
class OutputMapper(Protocol[O]):
    def map(self, obj: O) -> object: ...
