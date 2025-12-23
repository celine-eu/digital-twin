from __future__ import annotations
from typing import Protocol, runtime_checkable

from celine.dt.core.registry import DTRegistry


@runtime_checkable
class DTModule(Protocol):
    name: str
    version: str

    def register(self, registry: DTRegistry) -> None:
        ...
