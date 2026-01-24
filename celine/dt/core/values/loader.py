# celine/dt/core/values/loader.py
"""
Dynamic loading and registration of value fetchers.
"""
from __future__ import annotations

import logging

from celine.dt.core.loader import import_attr
from celine.dt.core.clients.registry import ClientsRegistry
from celine.dt.core.values.config import ValuesConfig
from celine.dt.core.values.registry import ValuesRegistry, FetcherDescriptor

logger = logging.getLogger(__name__)


def load_and_register_values(
    *,
    cfg: ValuesConfig,
    clients_registry: ClientsRegistry,
) -> ValuesRegistry:
    """
    Load and register all value fetchers.

    Resolves client references and output mappers, creating FetcherDescriptors
    that are ready for execution.

    Args:
        cfg: Values configuration containing fetcher specs
        clients_registry: Registry of available clients

    Returns:
        ValuesRegistry with all fetchers registered

    Raises:
        KeyError: If a referenced client doesn't exist
        ImportError: If an output mapper can't be imported
    """
    registry = ValuesRegistry()

    for spec in cfg.fetchers:
        logger.debug("Loading fetcher '%s' using client '%s'", spec.id, spec.client)

        # Resolve client
        if not clients_registry.has(spec.client):
            raise KeyError(
                f"Fetcher '{spec.id}' references unknown client '{spec.client}'. "
                f"Available clients: {clients_registry.list()}"
            )

        client = clients_registry.get(spec.client)

        # Resolve output mapper if specified
        output_mapper = None
        if spec.output_mapper:
            try:
                mapper_class = import_attr(spec.output_mapper)
                output_mapper = mapper_class()
                logger.debug(
                    "Loaded output mapper '%s' for fetcher '%s'",
                    spec.output_mapper,
                    spec.id,
                )
            except (ImportError, AttributeError) as exc:
                logger.error(
                    "Failed to load output mapper '%s' for fetcher '%s': %s",
                    spec.output_mapper,
                    spec.id,
                    exc,
                )
                raise

        descriptor = FetcherDescriptor(
            spec=spec,
            client=client,
            output_mapper=output_mapper,
        )

        registry.register(descriptor)

    logger.info(
        "Successfully registered %d value fetcher(s)",
        len(registry),
    )

    return registry
