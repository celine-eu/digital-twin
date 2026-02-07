# src/celine/dt/core/clients/loader.py
"""
Client loader reads config/clients.yaml and registers client instances.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.loader import import_attr, load_yaml_files, substitute_env_vars

logger = logging.getLogger(__name__)


def load_and_register_clients(
    *,
    patterns: Iterable[str],
    registry: ClientsRegistry,
    token_provider: Any | None = None,
) -> None:
    """Load client definitions from YAML and register live instances.

    Expected YAML::

        clients:
          dataset_api:
            class: celine.dt.core.clients.dataset_api:DatasetSqlApiClient
            config:
              base_url: "${DATASET_API_URL:-http://localhost:8001}"
              timeout: 30.0
    """
    yamls = load_yaml_files(patterns)
    if not yamls:
        logger.debug("No client config files matched: %s", list(patterns))
        return

    for data in yamls:
        for name, spec in (data.get("clients") or {}).items():
            class_path = spec.get("class")
            if not class_path:
                raise ValueError(f"Client '{name}' missing 'class' field")

            raw_config = substitute_env_vars(spec.get("config", {}))

            logger.info("Loading client '%s' from '%s'", name, class_path)
            try:
                cls = import_attr(class_path)
            except (ImportError, AttributeError):
                logger.exception("Failed to import client class '%s'", class_path)
                raise

            # Inject token_provider if the constructor accepts it
            kwargs = dict(raw_config)
            import inspect

            sig = inspect.signature(cls.__init__)
            if "token_provider" in sig.parameters:
                kwargs["token_provider"] = token_provider

            client = cls(**kwargs)
            registry.register(name, client)

    logger.info("Registered %d client(s): %s", len(registry.list()), registry.list())
