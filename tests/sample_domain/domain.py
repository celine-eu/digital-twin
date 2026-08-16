# tests/sample_domain/domain.py
"""
A domain laid out the way a real one is, used to exercise the parts of the runtime
that depend on module layout rather than on the class.

`router_discovery.discover` derives the routes package from the *domain class's
module path* — `celine.dt.domains.{pkg}.domain` → `celine.dt.domains.{pkg}.routes`.
A domain declared inline in a test file therefore has no discoverable routes and
silently gets none, which is why this fixture is a package on disk.
"""
from __future__ import annotations

from typing import ClassVar

from fastapi import Request

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain


class SampleCommunityDomain(DTDomain):
    """Permissive domain: resolves every entity, one templated fetcher."""

    name: ClassVar[str] = "test-community"
    domain_type: ClassVar[str] = "energy-community"
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str] = "/communities"
    entity_id_param: ClassVar[str] = "community_id"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [
            ValueFetcherSpec(
                id="consumption",
                client="mock",
                query=(
                    "SELECT * FROM consumption "
                    "WHERE community_id = '{{ entity.id }}'"
                    "{% if since %} AND ts >= :since{% endif %}"
                ),
                limit=100,
            ),
        ]


class ValidatingCommunityDomain(DTDomain):
    """A domain whose fetcher declares a payload schema, for the 400 path."""

    name: ClassVar[str] = "validating-community"
    domain_type: ClassVar[str] = "energy-community"
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str] = "/validating"
    entity_id_param: ClassVar[str] = "community_id"

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [
            ValueFetcherSpec(
                id="strict_consumption",
                client="mock",
                query="SELECT * FROM t WHERE zone = :zone AND days = :days",
                payload_schema={
                    "type": "object",
                    "required": ["zone"],
                    "properties": {
                        "zone": {"type": "string"},
                        "days": {"type": "integer", "default": 7},
                    },
                },
            ),
        ]


class StrictCommunityDomain(DTDomain):
    """Domain that rejects unknown entities, and enriches the ones it accepts."""

    name: ClassVar[str] = "strict-community"
    domain_type: ClassVar[str] = "energy-community"
    version: ClassVar[str] = "0.1.0"
    route_prefix: ClassVar[str] = "/strict"
    entity_id_param: ClassVar[str] = "community_id"

    KNOWN: ClassVar[set[str]] = {"abc-123", "xyz-456"}

    async def resolve_entity(
        self, entity_id: str, request: Request
    ) -> EntityInfo | None:
        if entity_id not in self.KNOWN:
            return None
        return EntityInfo(
            id=entity_id,
            domain_name=self.name,
            metadata={"region": "trentino"},
        )
