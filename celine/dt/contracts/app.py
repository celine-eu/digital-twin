from __future__ import annotations
from typing import Protocol, Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")


class DTApp(Protocol, Generic[I, O]):
    key: str
    version: str

    async def run(self, inputs: I, context: object) -> O: ...
