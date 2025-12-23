from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable
from pathlib import Path
import yaml
import logging
from glob import glob

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencySpec:
    name: str
    version: str


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    version: str
    import_path: str
    enabled: bool = True
    depends_on: list[DependencySpec] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModulesConfig:
    modules: list[ModuleSpec]
    ontology_active: str | None = None


def _load_yaml_files(patterns: Iterable[str]) -> list[dict[str, Any]]:
    files: list[Path] = []

    for pattern in patterns:
        matches = glob(pattern)
        files.extend(Path(m).resolve() for m in matches)

    files = sorted(set(files))

    logger.info("Loading module config files: %s", [str(f) for f in files])

    out: list[dict[str, Any]] = []
    for f in files:
        with f.open("r", encoding="utf-8") as fh:
            out.append(yaml.safe_load(fh) or {})
    return out


def load_modules_config(patterns: Iterable[str]) -> ModulesConfig:
    yamls = _load_yaml_files(patterns)

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
        specs.append(
            ModuleSpec(
                name=m["name"],
                version=m.get("version", ">=0"),
                import_path=m["import"],
                enabled=bool(m.get("enabled", True)),
                depends_on=deps,
                config=m.get("config") or {},
            )
        )

    return ModulesConfig(modules=specs, ontology_active=ontology_active)
