from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class OntologyBundle:
    ttl_files: list[str]
    jsonld_context_files: list[str]


def resolve_files(files: Iterable[str]) -> list[str]:
    out: list[str] = []
    for f in files:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(f"Ontology file not found: {f}")
        out.append(str(p))
    return out


def build_ontology_bundle(*, app_jsonld_files: list[str], app_ttl_files: list[str]) -> OntologyBundle:
    base_ttl = ["ontologies/celine.ttl", "ontologies/celine-dt-ext.ttl"]
    base_jsonld = ["ontologies/celine.jsonld"]

    ttl_files = resolve_files(base_ttl + app_ttl_files)
    jsonld_files = resolve_files(base_jsonld + app_jsonld_files)

    return OntologyBundle(ttl_files=ttl_files, jsonld_context_files=jsonld_files)
