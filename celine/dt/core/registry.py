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

    def register_app(
        self,
        app,
        *,
        input_mapper=None,
        output_mapper=None,
    ) -> None:
        self.apps[app.key] = AppDescriptor(
            app=app,
            input_mapper=input_mapper,
            output_mapper=output_mapper,
        )
        # Invalidate describe cache on registration
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

    # ---- introspection -------------------------------------------

    def describe_app(self, key: str) -> dict:
        return self._describe_app_cached(key)

    def _infer_mapper_model(self, mapper: object) -> type | None:
        for base in getattr(mapper.__class__, "__orig_bases__", ()):
            origin = get_origin(base)
            if origin is InputMapper or origin is OutputMapper:
                (model,) = get_args(base)
                return model
        return None

    @lru_cache(maxsize=None)
    def _describe_app_cached(self, key: str) -> dict:
        if key not in self.apps:
            raise KeyError(f"Unknown app '{key}'")

        desc = self.apps[key]

        input_model = self._infer_mapper_model(desc.input_mapper)
        if not input_model:
            input_model = getattr(desc.input_mapper, "input_model", None)

        output_model = self._infer_mapper_model(desc.output_mapper)
        if not output_model:
            output_model = getattr(desc.output_mapper, "output_model", None)

        return {
            "key": desc.app.key,
            "version": desc.app.version,
            "input_schema": (
                input_model.model_json_schema() if input_model is not None else None
            ),
            "output_schema": (
                output_model.model_json_schema() if output_model is not None else None
            ),
        }
