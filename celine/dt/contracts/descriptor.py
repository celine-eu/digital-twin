from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class AppDescriptor:
    app: Any
    defaults: Mapping[str, Any] = field(default_factory=dict)
