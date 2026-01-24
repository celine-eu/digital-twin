# celine/dt/core/modules/loader.py
from __future__ import annotations

import logging
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from celine.dt.contracts.module import DTModule
from celine.dt.core.registry import DTRegistry
from celine.dt.core.modules.config import ModulesConfig
from celine.dt.core.loader import import_attr

logger = logging.getLogger(__name__)


def load_and_register_modules(*, registry: DTRegistry, cfg: ModulesConfig) -> None:
    """
    Load and register DT modules.

    Args:
        registry: DT registry to register modules and apps
        cfg: Modules configuration

    Raises:
        ImportError: If module cannot be imported
        ValueError: If module validation fails
        RuntimeError: If module is missing required attributes
    """
    modules: dict[str, DTModule] = {}

    for spec in cfg.modules:
        if not spec.enabled:
            logger.debug("Skipping disabled module '%s'", spec.name)
            continue

        try:
            module_obj = import_attr(spec.import_path)
            module: DTModule = module_obj
        except Exception:
            logger.exception("Failed importing module %s", spec.import_path)
            raise

        required_attrs = ("name", "version", "register")
        for attr in required_attrs:
            if not hasattr(module, attr):
                raise RuntimeError(
                    f"Invalid DT module '{module.__class__.__name__}': missing '{attr}'"
                )

        if module.name != spec.name:
            raise ValueError(f"Module name mismatch: {spec.name} vs {module.name}")

        if Version(module.version) not in SpecifierSet(spec.version):
            raise ValueError(f"Module '{module.name}' version constraint failed")

        modules[module.name] = module

    # Check dependencies
    for spec in cfg.modules:
        if not spec.enabled:
            continue
        for dep in spec.depends_on:
            if dep.name not in modules:
                raise ValueError(
                    f"Module '{spec.name}' depends on missing '{dep.name}'"
                )
            if Version(modules[dep.name].version) not in SpecifierSet(dep.version):
                raise ValueError(f"Module '{spec.name}' dependency version mismatch")

    # Register all modules
    for name, module in modules.items():
        registry.register_module(name=name, version=module.version)
        try:
            module.register(registry)
        except Exception:
            logger.exception("Error registering module %s", name)
            raise

    if cfg.ontology_active:
        registry.set_active_ontology(cfg.ontology_active)

    logger.info("Registered %d module(s): %s", len(modules), list(modules.keys()))
