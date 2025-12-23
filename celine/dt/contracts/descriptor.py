
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class AppDescriptor:
    app: Any
    input_mapper: Any | None = None
    output_mapper: Any | None = None
