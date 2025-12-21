from __future__ import annotations

from pandas import DataFrame

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter
import yaml


logger = logging.getLogger(__name__)


class DTApp(Protocol):
    key: str
    version: str

    def ontology_ttl_files(self) -> list[str]: ...
    def ontology_jsonld_files(self) -> list[str]: ...
    def router(self) -> APIRouter | None: ...
    def configure(self, cfg: dict[str, Any]) -> None: ...
    def create_scenario(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def run(
        self, payload: dict[str, Any], df: DataFrame, options: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass
class AppRegistration:
    key: str
    enabled: bool
    import_path: str
    config: dict[str, Any]


class AppRegistry:
    def __init__(self) -> None:
        self._apps: dict[str, DTApp] = {}
        self._raw: list[AppRegistration] = []

    @property
    def apps(self) -> dict[str, DTApp]:
        return self._apps

    @property
    def registrations(self) -> list[AppRegistration]:
        return self._raw

    def load_from_yaml(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Apps config not found: {path}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        apps = data.get("apps", [])
        self._raw = []
        for a in apps:
            self._raw.append(
                AppRegistration(
                    key=a["key"],
                    enabled=bool(a.get("enabled", True)),
                    import_path=a["import"],
                    config=a.get("config", {}) or {},
                )
            )

    def _load_callable(self, import_path: str):
        # format: module.submodule:callable
        if ":" not in import_path:
            raise ValueError(
                f"Invalid import path '{import_path}'. Expected 'module:callable'"
            )
        mod_path, attr = import_path.split(":", 1)
        mod = importlib.import_module(mod_path)
        fn = getattr(mod, attr, None)
        if fn is None:
            raise ImportError(f"Callable '{attr}' not found in '{mod_path}'")
        return fn

    def register_enabled_apps(self) -> None:
        for reg in self._raw:
            if not reg.enabled:
                logger.info("DT app disabled", extra={"app": reg.key})
                continue
            factory = self._load_callable(reg.import_path)
            app = factory()
            if getattr(app, "key", None) != reg.key:
                raise ValueError(
                    f"App key mismatch. YAML='{reg.key}' factory='{getattr(app,'key',None)}'"
                )
            app.configure(reg.config)
            self._apps[reg.key] = app
            logger.info(
                "DT app registered", extra={"app": reg.key, "version": app.version}
            )
