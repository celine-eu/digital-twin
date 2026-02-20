# celine/dt/core/domain/loader.py
"""
Domain loader – imports domain classes, validates, and registers them.
"""
from __future__ import annotations

import logging
from typing import Any

from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.config import DomainsConfig
from celine.dt.core.domain.registry import DomainRegistry
from celine.dt.core.loader import import_attr

logger = logging.getLogger(__name__)


def load_and_register_domains(
    *,
    cfg: DomainsConfig,
    infrastructure: dict[str, Any],
) -> DomainRegistry:
    """Import domain classes, inject infrastructure, and register.

    Args:
        cfg: Domains configuration from YAML.
        infrastructure: Shared services dict (clients, broker, values, etc.).

    Returns:
        Populated ``DomainRegistry``.
    """
    registry = DomainRegistry()

    for spec in cfg.domains:
        if not spec.enabled:
            logger.info("Skipping disabled domain '%s'", spec.name)
            continue

        logger.info("Loading domain '%s' from '%s'", spec.name, spec.import_path)
        try:
            domain_obj = import_attr(spec.import_path)
        except (ImportError, AttributeError):
            logger.exception(f"Failed to import domain '{spec.name}'")
            continue

        if not isinstance(domain_obj, DTDomain):
            raise TypeError(
                f"Domain '{spec.name}' must be a DTDomain instance, "
                f"got {type(domain_obj).__name__}"
            )

        if domain_obj.name != spec.name:
            raise ValueError(
                f"Domain name mismatch: YAML says '{spec.name}', "
                f"class says '{domain_obj.name}'"
            )

        # Merge YAML overrides into infrastructure for this domain
        domain_infra = {**infrastructure, "overrides": spec.overrides}
        domain_obj.set_infrastructure(domain_infra)
        
        domain_obj._import_path = spec.import_path

        registry.register(domain_obj)

    logger.info("Registered %d domain(s)", len(registry))
    return registry
