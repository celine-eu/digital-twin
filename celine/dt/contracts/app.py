from __future__ import annotations
from typing import Any, Protocol


class DTApp(Protocol):
    key: str
    version: str

    async def run(self, inputs: Any, **context: Any) -> Any:
        ...
