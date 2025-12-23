from __future__ import annotations
import importlib
import logging
from typing import Any
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from celine.dt.contracts.module import DTModule
from celine.dt.core.registry import DTRegistry
from celine.dt.core.modules.config import ModulesConfig, ModuleSpec

logger = logging.getLogger(__name__)


def _import_attr(path: str) -> Any:
    if ":" not in path:
        raise ValueError(f"Invalid import path '{path}', expected 'module:attr'")
    mod_name, attr = path.split(":", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)


def load_and_register_modules(*, registry: DTRegistry, cfg: ModulesConfig) -> None:
    modules: dict[str, DTModule] = {}

    for spec in cfg.modules:
        if not spec.enabled:
            continue

        try:
            module_obj = _import_attr(spec.import_path)
            module: DTModule = module_obj
        except Exception:
            logger.exception("Failed importing module %s", spec.import_path)
            raise

        if module.name != spec.name:
            raise ValueError(f"Module name mismatch: {spec.name} vs {module.name}")

        if Version(module.version) not in SpecifierSet(spec.version):
            raise ValueError(f"Module '{module.name}' version constraint failed")

        modules[module.name] = module

    # dependencies
    for spec in cfg.modules:
        if not spec.enabled:
            continue
        for dep in spec.depends_on:
            if dep.name not in modules:
                raise ValueError(f"Module '{spec.name}' depends on missing '{dep.name}'")
            if Version(modules[dep.name].version) not in SpecifierSet(dep.version):
                raise ValueError(f"Module '{spec.name}' dependency version mismatch")

    # register
    for name, module in modules.items():
        registry.register_module(name=name, version=module.version)
        try:
            module.register(registry)
        except Exception:
            logger.exception("Error registering module %s", name)
            raise

    if cfg.ontology_active:
        registry.set_active_ontology(cfg.ontology_active)
