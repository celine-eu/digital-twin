from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass
class AdapterModule:
    app_key: str
    engine: str
    mapping_path: Path
    provides: list[str]


_ADAPTER_MODULES: Dict[str, AdapterModule] = {}


def register_adapter_module(module: AdapterModule) -> None:
    if module.app_key in _ADAPTER_MODULES:
        raise ValueError(f"Adapter module already registered for {module.app_key}")
    _ADAPTER_MODULES[module.app_key] = module


def get_adapter_module(app_key: str) -> AdapterModule:
    if app_key not in _ADAPTER_MODULES:
        raise KeyError(f"No adapter module registered for app {app_key}")
    return _ADAPTER_MODULES[app_key]
