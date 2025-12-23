from __future__ import annotations
import logging
from dataclasses import dataclass

from celine.dt.contracts.app import DTApp
from celine.dt.contracts.adapter import DTAdapter
from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.contracts.ontology import OntologyBundle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisteredModule:
    name: str
    version: str


class DTRegistry:
    def __init__(self) -> None:
        self.modules: dict[str, RegisteredModule] = {}
        self.apps: dict[str, DTApp] = {}
        self.adapters: dict[str, DTAdapter] = {}
        self.input_mappers: dict[str, InputMapper] = {}
        self.output_mappers: dict[str, OutputMapper] = {}
        self.ontologies: dict[str, OntologyBundle] = {}
        self.active_ontology: str | None = None

    def register_module(self, *, name: str, version: str) -> None:
        if name in self.modules:
            raise ValueError(f"Module already registered: {name}")
        self.modules[name] = RegisteredModule(name, version)
        logger.info("Registered module %s (%s)", name, version)

    def register_app(self, app: DTApp) -> None:
        if app.key in self.apps:
            raise ValueError(f"App already registered: {app.key}")
        self.apps[app.key] = app
        logger.info("Registered app %s (%s)", app.key, app.version)

    def register_adapter(self, name: str, adapter: DTAdapter) -> None:
        if name in self.adapters:
            raise ValueError(f"Adapter already registered: {name}")
        self.adapters[name] = adapter
        logger.info("Registered adapter %s", name)

    def register_input_mapper(self, name: str, mapper: InputMapper) -> None:
        if name in self.input_mappers:
            raise ValueError(f"InputMapper already registered: {name}")
        self.input_mappers[name] = mapper
        logger.info("Registered input mapper %s", name)

    def register_output_mapper(self, name: str, mapper: OutputMapper) -> None:
        if name in self.output_mappers:
            raise ValueError(f"OutputMapper already registered: {name}")
        self.output_mappers[name] = mapper
        logger.info("Registered output mapper %s", name)

    def register_ontology_bundle(self, bundle: OntologyBundle) -> None:
        if bundle.name in self.ontologies:
            raise ValueError(f"Ontology bundle already registered: {bundle.name}")
        self.ontologies[bundle.name] = bundle
        logger.info("Registered ontology bundle %s", bundle.name)

    def set_active_ontology(self, name: str) -> None:
        if name not in self.ontologies:
            raise KeyError(f"Unknown ontology bundle '{name}'")
        self.active_ontology = name
        logger.info("Active ontology set to %s", name)
