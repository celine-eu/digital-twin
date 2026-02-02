from __future__ import annotations
import json
import logging
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from celine.dt.contracts.ontology import OntologyResource

logger = logging.getLogger(__name__)


def load_jsonld(resource: OntologyResource) -> dict:
    ref = resource.ref
    parsed = urlparse(ref)

    try:
        if parsed.scheme in ("http", "https"):
            with urlopen(ref) as resp:
                return json.loads(resp.read().decode("utf-8"))
        else:
            return json.loads(Path(ref).read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed loading JSON-LD from %s", ref)
        raise
