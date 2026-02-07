# celine/dt/contracts/entity.py
"""
Entity contracts for domain-scoped resources.

An entity is the addressable resource within a domain (e.g. a specific
energy community or a specific participant). The entity info travels
through the entire request lifecycle and is available in templates,
handlers, and custom routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityInfo:
    """Resolved entity within a domain request.

    Attributes:
        id: The entity identifier extracted from the URL path.
        domain_name: Name of the domain that owns this entity.
        metadata: Arbitrary key-value data populated by the domain's
            ``resolve_entity`` hook. Available in Jinja query templates
            as ``{{ entity.metadata.<key> }}``.
    """

    id: str
    domain_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
