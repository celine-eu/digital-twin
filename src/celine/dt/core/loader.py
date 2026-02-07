# celine/dt/core/loader.py
"""
Shared utilities for dynamic loading and configuration processing.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import re
import sys
from glob import glob
from pathlib import Path
from typing import Any, Iterable

import yaml

logger = logging.getLogger(__name__)

ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def import_attr(path: str) -> Any:
    """Dynamically import ``module.path:attribute``.

    Reuses already-loaded modules when the origin file matches,
    avoiding double-load issues in test runners.
    """
    if ":" not in path:
        raise ValueError(f"Invalid import path '{path}', expected 'module:attr'")

    mod_name, attr = path.split(":", 1)

    mod = sys.modules.get(mod_name)
    if mod is None:
        try:
            spec = importlib.util.find_spec(mod_name)
        except Exception:
            spec = None

        origin = getattr(spec, "origin", None) if spec else None
        if origin:
            for loaded in sys.modules.values():
                if getattr(loaded, "__file__", None) == origin:
                    mod = loaded
                    break

    if mod is None:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            logger.error("Failed to import module '%s'", mod_name)
            raise ImportError(f"Cannot import module '{mod_name}'")

    try:
        return getattr(mod, attr)
    except AttributeError:
        raise AttributeError(f"Module '{mod_name}' has no attribute '{attr}'")


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ``${VAR}`` / ``${VAR:-default}`` in config values."""
    if isinstance(value, str):
        return _substitute_string(value)
    if isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


def _substitute_string(value: str) -> str:
    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_value = os.environ.get(var_name)
        if env_value is not None:
            return env_value
        if default is not None:
            return default
        raise ValueError(f"Environment variable '{var_name}' not set, no default provided")

    return ENV_VAR_PATTERN.sub(_replacer, value)


def load_yaml_files(patterns: Iterable[str]) -> list[dict[str, Any]]:
    """Load YAML files matching glob patterns, sorted for determinism."""
    files: list[Path] = []
    for pattern in patterns:
        files.extend(Path(m).resolve() for m in glob(pattern))
    files = sorted(set(files))

    if not files:
        logger.debug("No config files matched patterns: %s", list(patterns))
        return []

    out: list[dict[str, Any]] = []
    for f in files:
        try:
            with f.open("r", encoding="utf-8") as fh:
                content = yaml.safe_load(fh) or {}
                out.append(content)
        except Exception:
            logger.exception("Failed to load YAML '%s'", f)
            raise
    return out
