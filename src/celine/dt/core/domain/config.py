# celine/dt/core/domain/config.py
"""
Domain configuration loading.

Domains are declared in code (DTDomain subclasses) and optionally
overridden by YAML for production tuning (broker hosts, feature flags,
client URLs, etc.).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from celine.dt.core.loader import load_yaml_files, substitute_env_vars

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainSpec:
    """YAML-declared domain specification."""

    name: str
    import_path: str
    enabled: bool = True
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainsConfig:
    domains: list[DomainSpec] = field(default_factory=list)


def load_domains_config(patterns: Iterable[str]) -> DomainsConfig:
    """Load domain declarations from YAML.

    Expected structure::

        domains:
          - name: it-energy-community
            import: celine.dt.domains.energy_community.domain:domain
            enabled: true
            overrides:
              broker: celine_mqtt
              feature_flags:
                enable_ev_charging: true
    """
    yamls = load_yaml_files(patterns)
    domains_map: dict[str, dict[str, Any]] = {}

    for data in yamls:
        for d in data.get("domains", []):
            raw_overrides = substitute_env_vars(d.get("overrides", {}))
            domains_map[d["name"]] = {**d, "overrides": raw_overrides}

    specs: list[DomainSpec] = []
    for raw in domains_map.values():
        specs.append(
            DomainSpec(
                name=raw["name"],
                import_path=raw["import"],
                enabled=raw.get("enabled", True),
                overrides=raw.get("overrides", {}),
            )
        )

    logger.info("Loaded %d domain spec(s): %s", len(specs), [s.name for s in specs])
    return DomainsConfig(domains=specs)
