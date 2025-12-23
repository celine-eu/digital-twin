from __future__ import annotations
from typing import Any, Protocol


class InputMapper(Protocol):
    def map(self, raw: Any, **context: Any) -> Any:
        ...


class OutputMapper(Protocol):
    ontology: str

    def map(self, obj: Any, **context: Any) -> dict[str, Any]:
        ...
