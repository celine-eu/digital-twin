from __future__ import annotations
from celine.dt.contracts.ontology import OntologyBundle, OntologyResource

celine_bundle = OntologyBundle(
    name="celine",
    ttl=[OntologyResource("https://celine-eu.github.io/ontologies/celine.ttl")],
    jsonld=[OntologyResource("https://celine-eu.github.io/ontologies/celine.jsonld")],
)
