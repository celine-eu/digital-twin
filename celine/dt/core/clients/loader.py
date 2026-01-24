# celine/dt/core/clients/loader.py
"""
Dynamic loading and registration of data clients.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from celine.dt.core.loader import import_attr
from celine.dt.core.clients.config import ClientsConfig
from celine.dt.core.clients.registry import ClientsRegistry

logger = logging.getLogger(__name__)


def load_and_register_clients(
    *,
    cfg: ClientsConfig,
    injectable_services: Mapping[str, Any] | None = None,
) -> ClientsRegistry:
    """
    Load client classes and instantiate them with configuration.

    Args:
        cfg: Clients configuration containing specs for all clients
        injectable_services: Dict of service name -> instance that can be
            injected into clients (e.g., {'token_provider': token_provider})

    Returns:
        ClientsRegistry with all clients registered

    Raises:
        ImportError: If a client class cannot be imported
        TypeError: If client instantiation fails
        ValueError: If injectable service is missing
    """
    injectable_services = injectable_services or {}
    registry = ClientsRegistry()

    for spec in cfg.clients:
        logger.info("Loading client '%s' from '%s'", spec.name, spec.class_path)

        try:
            client_class = import_attr(spec.class_path)
        except (ImportError, AttributeError) as exc:
            logger.error("Failed to import client class '%s'", spec.class_path)
            raise

        # Build kwargs from config + injected services
        kwargs = dict(spec.config)

        for service_name in spec.inject:
            if service_name not in injectable_services:
                raise ValueError(
                    f"Client '{spec.name}' requires injectable service "
                    f"'{service_name}' but it was not provided"
                )
            kwargs[service_name] = injectable_services[service_name]

        # Instantiate the client
        try:
            client_instance = client_class(**kwargs)
        except TypeError as exc:
            logger.error(
                "Failed to instantiate client '%s' with kwargs %s: %s",
                spec.name,
                list(kwargs.keys()),
                exc,
            )
            raise TypeError(
                f"Failed to instantiate client '{spec.name}': {exc}"
            ) from exc

        registry.register(spec.name, client_instance)

    logger.info(
        "Successfully loaded %d client(s): %s",
        len(registry),
        registry.list(),
    )

    return registry
