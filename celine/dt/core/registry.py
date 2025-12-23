from __future__ import annotations

from typing import Dict, Optional, get_args, get_origin
from functools import lru_cache

from celine.dt.contracts.descriptor import AppDescriptor
from celine.dt.contracts.mapper import InputMapper, OutputMapper


class DTRegistry:
    def __init__(self) -> None:
        self.apps: Dict[str, AppDescriptor] = {}
        self.modules: Dict[str, str] = {}
        self.active_ontology: Optional[str] = None

    # ---- modules -------------------------------------------------

    def register_module(self, name: str, version: str) -> None:
        self.modules[name] = version

    # ---- ontology ------------------------------------------------

    def set_active_ontology(self, name: Optional[str]) -> None:
        self.active_ontology = name

    # ---- apps ----------------------------------------------------
    def register_app(self, app) -> None:
        self.apps[app.key] = AppDescriptor(app=app)
        self._describe_app_cached.cache_clear()

    # ---- listing -------------------------------------------------

    def list_apps(self) -> list[dict[str, str]]:
        return [
            {
                "key": desc.app.key,
                "version": desc.app.version,
            }
            for desc in self.apps.values()
        ]

    def describe_app(self, key: str) -> dict:
        return self._describe_app_cached(key)

    @lru_cache(maxsize=None)
    def _describe_app_cached(self, key: str) -> dict:
        desc = self.apps[key]
        app = desc.app

        return {
            "key": desc.app.key,
            "version": desc.app.version,
            "input_schema": app.config_type.model_json_schema(),
            "output_schema": app.result_type.model_json_schema(),
        }
