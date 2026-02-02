from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class OntologyResource:
    """Local path or remote URL."""
    ref: str


@dataclass(frozen=True)
class OntologyBundle:
    name: str
    ttl: Sequence[OntologyResource]
    jsonld: Sequence[OntologyResource]
