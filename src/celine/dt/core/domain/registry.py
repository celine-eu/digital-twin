# celine/dt/core/domain/registry.py
"""
Domain registry – stores and retrieves domain instances.
"""
from __future__ import annotations

import logging
from typing import Iterator

from celine.dt.core.domain.base import DTDomain

logger = logging.getLogger(__name__)


class DomainRegistry:
    """Thread-safe registry of DTDomain instances."""

    def __init__(self) -> None:
        self._domains: dict[str, DTDomain] = {}

    def register(self, domain: DTDomain) -> None:
        if domain.name in self._domains:
            raise ValueError(f"Domain '{domain.name}' is already registered")

        # Prevent two domains claiming the same route prefix
        existing = self.get_by_prefix(domain.route_prefix)
        if existing is not None:
            raise ValueError(
                f"Domain '{domain.name}' wants prefix '{domain.route_prefix}' "
                f"but '{existing.name}' already owns it"
            )

        self._domains[domain.name] = domain

    def get(self, name: str) -> DTDomain:
        try:
            return self._domains[name]
        except KeyError:
            raise KeyError(
                f"Domain '{name}' not found. Available: {list(self._domains)}"
            )

    def get_by_prefix(self, prefix: str) -> DTDomain | None:
        """Look up a domain by its route prefix."""
        for d in self._domains.values():
            if d.route_prefix == prefix:
                return d
        return None

    def list(self) -> list[dict]:
        return [d.describe() for d in self._domains.values()]

    def __iter__(self) -> Iterator[DTDomain]:
        return iter(self._domains.values())

    def __len__(self) -> int:
        return len(self._domains)

    def __contains__(self, name: str) -> bool:
        return name in self._domains
