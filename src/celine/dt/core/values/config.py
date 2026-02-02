# celine/dt/core/values/config.py
"""
Configuration models and loading for value fetchers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from celine.dt.core.loader import load_yaml_files
from celine.dt.core.modules.config import ModulesConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValueFetcherSpec:
    """
    Specification for a value fetcher.

    Attributes:
        id: Unique identifier for this fetcher (may include namespace prefix)
        client: Name of the client to use (from clients registry)
        query: Query template with :param placeholders (client-specific)
        limit: Default limit for results
        offset: Default offset for pagination
        payload_schema: Optional JSON Schema for validating input parameters
        output_mapper: Optional import path to output mapper class
    """

    id: str
    client: str
    query: Any = None  # Can be string (SQL) or dict (client-specific)
    limit: int = 100
    offset: int = 0
    payload_schema: dict[str, Any] | None = None
    output_mapper: str | None = None


@dataclass(frozen=True)
class ValuesConfig:
    """
    Container for all value fetcher specifications.

    Attributes:
        fetchers: List of fetcher specifications
    """

    fetchers: list[ValueFetcherSpec] = field(default_factory=list)


def _parse_fetcher_spec(
    fetcher_id: str,
    raw: dict[str, Any],
) -> ValueFetcherSpec:
    """
    Parse a single fetcher specification from raw YAML dict.

    Args:
        fetcher_id: The fetcher identifier (may include namespace)
        raw: Raw configuration dict from YAML

    Returns:
        Parsed ValueFetcherSpec

    Raises:
        ValueError: If required fields are missing
    """
    if "client" not in raw:
        raise ValueError(f"Fetcher '{fetcher_id}' missing required 'client' field")

    return ValueFetcherSpec(
        id=fetcher_id,
        client=raw["client"],
        query=raw.get("query"),
        limit=raw.get("limit", 100),
        offset=raw.get("offset", 0),
        payload_schema=raw.get("payload"),
        output_mapper=raw.get("output_mapper"),
    )


def load_values_config(
    patterns: Iterable[str],
    modules_cfg: ModulesConfig | None = None,
) -> ValuesConfig:
    """
    Load values configuration from YAML files and module configs.

    Expected YAML structure in values.yaml:
    ```yaml
    values:
      fetcher_id:
        client: dataset_api
        query: SELECT * FROM table WHERE col = :param
        limit: 10
        payload:
          type: object
          properties:
            param:
              type: string
        output_mapper: module.path:MapperClass
    ```

    Module-defined values are namespaced as 'module_name.fetcher_id'.
    Root-level values (from values.yaml) keep their original ID.

    Args:
        patterns: Glob patterns for values YAML config files
        modules_cfg: Optional modules config to extract module-defined values

    Returns:
        ValuesConfig with all fetcher specifications

    Raises:
        ValueError: If configuration is invalid
    """
    fetchers_map: dict[str, dict[str, Any]] = {}

    # 1. Load from values.yaml files (root level, no namespace)
    yamls = load_yaml_files(patterns) or []
    for data in yamls:
        values = data.get("values") or {}
        for fetcher_id, spec in values.items():
            fetchers_map[fetcher_id] = spec  # later files override

    # 2. Load from modules config (namespaced by module name)
    if modules_cfg:
        for module_spec in modules_cfg.modules:
            if not module_spec.enabled:
                continue

            for fetcher_id, spec in module_spec.values.items():
                namespaced_id = f"{module_spec.name}.{fetcher_id}"
                fetchers_map[namespaced_id] = spec
                logger.debug(
                    "Loaded module-scoped fetcher '%s' from module '%s'",
                    namespaced_id,
                    module_spec.name,
                )

    # 3. Parse all specs
    specs: list[ValueFetcherSpec] = []
    for fetcher_id, raw in fetchers_map.items():
        try:
            spec = _parse_fetcher_spec(fetcher_id, raw)
            specs.append(spec)
        except ValueError as exc:
            logger.error("Failed to parse fetcher '%s': %s", fetcher_id, exc)
            raise

    logger.info(
        "Loaded %d value fetcher(s): %s",
        len(specs),
        [s.id for s in specs],
    )

    return ValuesConfig(fetchers=specs)
