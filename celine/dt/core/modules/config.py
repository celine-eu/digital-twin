# celine/dt/core/modules/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable

import logging

from celine.dt.core.loader import load_yaml_files

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencySpec:
    """Module dependency specification."""

    name: str
    version: str


@dataclass(frozen=True)
class ModuleSpec:
    """
    Specification for a DT module.

    Attributes:
        name: Unique module identifier
        version: Semantic version constraint
        import_path: Import path in format 'module:attr'
        enabled: Whether the module is enabled
        depends_on: List of module dependencies
        config: Module-specific configuration
        values: Module-scoped value fetchers (namespaced as module_name.fetcher_id)
    """

    name: str
    version: str
    import_path: str
    enabled: bool = True
    depends_on: list[DependencySpec] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModulesConfig:
    """
    Container for all module specifications.

    Attributes:
        modules: List of module specifications
        ontology_active: Active ontology name (optional)
    """

    modules: list[ModuleSpec]
    ontology_active: str | None = None


def load_modules_config(patterns: Iterable[str]) -> ModulesConfig:
    """
    Load modules configuration from YAML files.

    Expected YAML structure:
    ```yaml
    modules:
      - name: my-module
        version: ">=1.0.0"
        import: my.module:module
        enabled: true
        depends_on:
          - name: other-module
            version: ">=1.0.0"
        config:
          some_key: some_value
          values:
            my_fetcher:
              client: dataset_api
              query: SELECT * FROM table

    ontology:
      active: celine
    ```

    Later files override earlier ones when module names collide.

    Args:
        patterns: Glob patterns for YAML config files

    Returns:
        ModulesConfig with all module specifications
    """
    yamls = load_yaml_files(patterns)

    modules_map: Dict[str, dict[str, Any]] = {}
    ontology_active: str | None = None

    for data in yamls:
        for m in data.get("modules", []):
            modules_map[m["name"]] = m  # override by later files

        ont = data.get("ontology") or {}
        if "active" in ont:
            ontology_active = ont["active"]

    specs: list[ModuleSpec] = []
    for m in modules_map.values():
        deps = [DependencySpec(**d) for d in (m.get("depends_on") or [])]

        # Config is for module-specific settings
        config = m.get("config") or {}

        # Values define module-scoped fetchers (namespaced later)
        values = m.get("values") or {}

        specs.append(
            ModuleSpec(
                name=m["name"],
                version=m.get("version", ">=0"),
                import_path=m["import"],
                enabled=bool(m.get("enabled", True)),
                depends_on=deps,
                config=config,
                values=values,
            )
        )

    logger.info(
        "Loaded %d module specification(s): %s",
        len(specs),
        [s.name for s in specs],
    )

    return ModulesConfig(modules=specs, ontology_active=ontology_active)
