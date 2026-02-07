# tests/test_domain_registry.py
"""
Unit tests for domain registry and configuration.
"""
import pytest
from typing import ClassVar

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry


class DomainA(DTDomain):
    name: ClassVar[str] = "domain-a"
    domain_type: ClassVar[str] = "test"
    version: ClassVar[str] = "1.0.0"
    route_prefix: ClassVar[str] = "/a"
    entity_id_param: ClassVar[str] = "a_id"


class DomainB(DTDomain):
    name: ClassVar[str] = "domain-b"
    domain_type: ClassVar[str] = "test"
    version: ClassVar[str] = "1.0.0"
    route_prefix: ClassVar[str] = "/b"
    entity_id_param: ClassVar[str] = "b_id"


class TestDomainRegistry:
    def test_register_and_get(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        assert "domain-a" in reg
        d = reg.get("domain-a")
        assert d.route_prefix == "/a"

    def test_duplicate_raises(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(DomainA())

    def test_missing_raises(self):
        reg = DomainRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nope")

    def test_list(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        reg.register(DomainB())
        listed = reg.list()
        assert len(listed) == 2
        names = {d["name"] for d in listed}
        assert names == {"domain-a", "domain-b"}

    def test_get_by_prefix(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        reg.register(DomainB())
        assert reg.get_by_prefix("/a").name == "domain-a"
        assert reg.get_by_prefix("/b").name == "domain-b"
        assert reg.get_by_prefix("/c") is None

    def test_iter(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        reg.register(DomainB())
        names = [d.name for d in reg]
        assert len(names) == 2


class TestDomainBase:
    @pytest.mark.asyncio
    async def test_default_resolve(self):
        d = DomainA()
        entity = await d.resolve_entity("test-id")
        assert entity is not None
        assert entity.id == "test-id"
        assert entity.domain_name == "domain-a"

    def test_describe(self):
        d = DomainA()
        desc = d.describe()
        assert desc["name"] == "domain-a"
        assert desc["route_prefix"] == "/a"
        assert desc["entity_id_param"] == "a_id"
