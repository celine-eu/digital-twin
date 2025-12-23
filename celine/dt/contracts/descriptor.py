from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class AppDescriptor:
    app: Any
    input_mapper: Any | None = None
    output_mapper: Any | None = None
    defaults: Mapping[str, Any] = {}
    datasts: list[str] = []
