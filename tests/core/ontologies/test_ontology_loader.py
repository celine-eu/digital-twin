from __future__ import annotations

import json
from pathlib import Path

from celine.dt.contracts.ontology import OntologyResource
from celine.dt.core.ontologies.loader import load_jsonld


def test_load_jsonld_from_file(tmp_path: Path) -> None:
    p = tmp_path / "ctx.jsonld"
    p.write_text(json.dumps({"@context": {"x": "y"}}), encoding="utf-8")

    data = load_jsonld(OntologyResource(str(p)))
    assert data["@context"]["x"] == "y"
