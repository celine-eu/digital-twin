# celine/dt/core/clients/config.py
"""
Configuration models and loading for data clients.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from celine.dt.core.loader import load_yaml_files, substitute_env_vars

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientSpec:
    """
    Specification for a data client.

    Attributes:
        name: Unique identifier for this client
        class_path: Import path in format 'module:ClassName'
        inject: List of service names to inject from app state
        config: Configuration dict to pass to client constructor
    """

    name: str
    class_path: str
    inject: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientsConfig:
    """
    Container for all client specifications.

    Attributes:
        clients: List of client specifications
    """

    clients: list[ClientSpec] = field(default_factory=list)


def load_clients_config(patterns: Iterable[str]) -> ClientsConfig:
    """
    Load clients configuration from YAML files.

    Expected YAML structure:
    ```yaml
    clients:
      client_name:
        class: module.path:ClassName
        inject:
          - token_provider
        config:
          base_url: "${BASE_URL}"
          timeout: 30.0
    ```

    Environment variables in config values are substituted:
    - ${VAR} - required, raises if not set
    - ${VAR:-default} - optional with default

    Args:
        patterns: Glob patterns for YAML config files

    Returns:
        ClientsConfig with all client specifications

    Raises:
        ValueError: If configuration is invalid or env vars missing
    """
    yamls = load_yaml_files(patterns)

    clients_map: dict[str, dict[str, Any]] = {}

    for data in yamls:
        for name, spec in data.get("clients", {}).items():
            clients_map[name] = spec  # later files override

    specs: list[ClientSpec] = []

    for name, raw in clients_map.items():
        if "class" not in raw:
            raise ValueError(f"Client '{name}' missing required 'class' field")

        # Substitute env vars in config
        config = raw.get("config", {})
        try:
            config = substitute_env_vars(config)
        except ValueError as exc:
            raise ValueError(f"Client '{name}' config error: {exc}") from exc

        specs.append(
            ClientSpec(
                name=name,
                class_path=raw["class"],
                inject=raw.get("inject", []),
                config=config,
            )
        )

    logger.info("Loaded %d client specification(s): %s", len(specs), [s.name for s in specs])

    return ClientsConfig(clients=specs)
