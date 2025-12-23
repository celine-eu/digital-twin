from __future__ import annotations
from typing import Any, Protocol


class DTAdapter(Protocol):
    async def fetch(self, request: dict[str, Any], **context: Any) -> Any:
        ...
