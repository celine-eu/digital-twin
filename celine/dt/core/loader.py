# celine/dt/core/loader.py
"""
Shared utilities for dynamic loading and configuration processing.
"""
from __future__ import annotations

import importlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable
import importlib.util
import sys

import yaml
from glob import glob

logger = logging.getLogger(__name__)

# Pattern for environment variable substitution: ${VAR} or ${VAR:-default}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def import_attr(path: str) -> Any:
    """
    Dynamically import an attribute from a module.

    Args:
        path: Import path in format 'module.path:attribute'

    Returns:
        The imported attribute

    Raises:
        ValueError: If path format is invalid
        ImportError: If module cannot be imported
        AttributeError: If attribute doesn't exist
    """
    if ":" not in path:
        raise ValueError(f"Invalid import path '{path}', expected 'module:attr'")

    mod_name, attr = path.split(":", 1)

    # Avoid loading the same source file twice under different module names.
    # This can happen in test runners (notably pytest) depending on import mode.
    # If the target module spec resolves to a file that is already loaded, reuse it.
    mod = sys.modules.get(mod_name)
    if mod is None:
        try:
            spec = importlib.util.find_spec(mod_name)
        except Exception:
            spec = None

        origin = getattr(spec, "origin", None) if spec else None
        if origin:
            for loaded in sys.modules.values():
                loaded_origin = getattr(loaded, "__file__", None)
                if loaded_origin and loaded_origin == origin:
                    logger.debug(
                        "Reusing already-loaded module '%s' for '%s' (same origin: %s)",
                        getattr(loaded, "__name__", "<unknown>"),
                        mod_name,
                        origin,
                    )
                    mod = loaded
                    break

    try:
        if mod is None:
            mod = importlib.import_module(mod_name)
    except ImportError as exc:
        logger.error("Failed to import module '%s'", mod_name)
        raise ImportError(f"Cannot import module '{mod_name}'") from exc

    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        logger.error("Module '%s' has no attribute '%s'", mod_name, attr)
        raise AttributeError(f"Module '{mod_name}' has no attribute '{attr}'") from exc


def substitute_env_vars(value: Any) -> Any:
    """
    Recursively substitute environment variables in configuration values.

    Supports:
        - ${VAR} - substitutes with env var, raises if not set
        - ${VAR:-default} - substitutes with env var or default if not set

    Args:
        value: Configuration value (string, dict, list, or other)

    Returns:
        Value with environment variables substituted

    Raises:
        ValueError: If required env var is not set and no default provided
    """
    if isinstance(value, str):
        return _substitute_string(value)
    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    else:
        return value


def _substitute_string(value: str) -> str:
    """Substitute environment variables in a single string."""

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)

        env_value = os.environ.get(var_name)

        if env_value is not None:
            return env_value
        elif default is not None:
            return default
        else:
            raise ValueError(
                f"Environment variable '{var_name}' is not set and no default provided"
            )

    return ENV_VAR_PATTERN.sub(replacer, value)


def load_yaml_files(patterns: Iterable[str]) -> list[dict[str, Any]]:
    """
    Load multiple YAML files matching glob patterns.

    Files are loaded in sorted order. Later files can override earlier ones
    when merged by the caller.

    Args:
        patterns: Glob patterns for YAML files

    Returns:
        List of parsed YAML documents
    """
    files: list[Path] = []

    for pattern in patterns:
        matches = glob(pattern)
        files.extend(Path(m).resolve() for m in matches)

    files = sorted(set(files))

    if not files:
        logger.warning("No config files found matching patterns: %s", list(patterns))
        return []

    logger.info("Loading config files: %s", [str(f) for f in files])

    out: list[dict[str, Any]] = []
    for f in files:
        try:
            with f.open("r", encoding="utf-8") as fh:
                content = yaml.safe_load(fh) or {}
                out.append(content)
        except Exception as exc:
            logger.error("Failed to load YAML file '%s': %s", f, exc)
            raise

    return out
