# celine/dt/contracts/ontology.py
"""
Ontology fetcher contracts.

An ontology spec is a named concept view that composes one or more value
fetcher bindings into a single JSON-LD document.  Each binding maps a
fetcher to its CELINE mapping spec YAML and describes how entity metadata
is projected into mapper context variables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OntologyFetcherBinding:
    """One fetcher contributing nodes to a concept view.

    Attributes:
        fetcher_id: Local fetcher ID (without domain namespace prefix).
        mapper_spec_path: Absolute path to the YAML mapping spec.
        context_vars: Mapping of entity.metadata key → mapper context var
            name.  Leave empty when all context comes from row fields.
    """

    fetcher_id: str
    mapper_spec_path: Path
    context_vars: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OntologySpec:
    """A named concept view composed of one or more fetcher bindings.

    All bindings are fetched in parallel; their JSON-LD nodes are merged
    into a single ``@graph`` before being wrapped with ``@context``.

    Attributes:
        id: Local spec identifier (e.g. ``"rec_energy"``).
        bindings: One or more fetcher bindings that contribute nodes.
        description: Human-readable description for discovery endpoints.
        payload_schema: Optional JSON Schema applied to all bindings.
    """

    id: str
    bindings: list[OntologyFetcherBinding]
    description: str = ""
    payload_schema: dict[str, Any] | None = None
