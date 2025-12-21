from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonld_contexts(context_files: list[str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for fp in context_files:
        data = json.loads(Path(fp).read_text(encoding="utf-8"))
        # Accept either {"@context": {...}} or raw {"term": "..."}
        if "@context" in data:
            contexts.append(data["@context"])
        else:
            contexts.append(data)
    return contexts


def with_context(payload: dict[str, Any], context_files: list[str]) -> dict[str, Any]:
    contexts = load_jsonld_contexts(context_files)
    payload = dict(payload)
    payload["@context"] = contexts
    return payload
