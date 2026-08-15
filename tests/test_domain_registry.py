# tests/test_domain_registry.py
"""
Unit tests for domain registry and configuration.
"""
import pytest
from typing import ClassVar

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry

from tests.conftest import make_request


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
    # @verifies REQ-1001
    def test_register_and_get(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        assert "domain-a" in reg
        d = reg.get("domain-a")
        assert d.route_prefix == "/a"

    # @verifies REQ-1001
    def test_duplicate_raises(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(DomainA())

    # @verifies REQ-1001
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

    # @verifies REQ-1002
    def test_duplicate_prefix_raises(self):
        """Two domains cannot claim the same route prefix.

        Not a duplicate-name check: these have distinct names. Without it the second
        domain's routes would shadow the first's and `match_path` would pick one of
        them arbitrarily.
        """

        class DomainAClone(DTDomain):
            name: ClassVar[str] = "domain-a-clone"
            domain_type: ClassVar[str] = "test"
            route_prefix: ClassVar[str] = "/a"
            entity_id_param: ClassVar[str] = "a_id"

        reg = DomainRegistry()
        reg.register(DomainA())
        with pytest.raises(ValueError, match="already owns it"):
            reg.register(DomainAClone())

    def test_get_by_type(self):
        reg = DomainRegistry()
        reg.register(DomainA())
        assert reg.get_by_type("test").name == "domain-a"
        with pytest.raises(KeyError, match="No domain with type"):
            reg.get_by_type("nope")


class TestMatchPath:
    """`match_path` is what maps an inbound URL back to its domain.

    Every context-dependent route resolves its domain through it, so a wrong answer
    here is a request served by the wrong domain rather than an error.
    """

    def _registry(self) -> DomainRegistry:
        class Nested(DTDomain):
            name: ClassVar[str] = "nested"
            domain_type: ClassVar[str] = "test"
            route_prefix: ClassVar[str] = "/a/it"
            entity_id_param: ClassVar[str] = "nested_id"

        reg = DomainRegistry()
        reg.register(DomainA())
        reg.register(DomainB())
        reg.register(Nested())
        return reg

    # @verifies REQ-1010
    def test_longest_prefix_wins(self):
        reg = self._registry()
        assert reg.match_path("/a/it/rec-1/values").name == "nested"
        assert reg.match_path("/a/rec-1/values").name == "domain-a"

    # @verifies REQ-1010
    def test_exact_prefix_matches(self):
        assert self._registry().match_path("/b").name == "domain-b"

    # @verifies REQ-1012
    def test_trailing_slash_ignored(self):
        assert self._registry().match_path("/b/").name == "domain-b"

    # @verifies REQ-1011
    def test_partial_segment_does_not_match(self):
        """`/about` must not match the domain mounted at `/a`.

        The check is segment-wise (`startswith(rp + "/")`), not a bare string
        prefix. A bare prefix test would hand `/about` to domain-a.
        """
        assert self._registry().match_path("/about") is None

    # @verifies REQ-1013
    def test_unknown_path_is_none(self):
        assert self._registry().match_path("/zzz/1") is None
        assert self._registry().match_path("") is None


class TestDomainBase:
    @pytest.mark.asyncio
    # @verifies REQ-1030
    async def test_default_resolve(self):
        d = DomainA()
        entity = await d.resolve_entity("test-id", make_request("/a/test-id"))
        assert entity is not None
        assert entity.id == "test-id"
        assert entity.domain_name == "domain-a"
        assert entity.metadata == {}

    @pytest.mark.asyncio
    # @verifies REQ-1033
    async def test_default_resolve_accepts_anything(self):
        """The base class validates nothing — rejection is a domain's own job.

        Worth pinning: a domain that forgets to override resolve_entity serves every
        entity id in the URL space, which is a permissive default and not an obvious
        one.
        """
        d = DomainA()
        entity = await d.resolve_entity("../../etc/passwd", make_request("/a/x"))
        assert entity is not None
        assert entity.id == "../../etc/passwd"

    def test_describe(self):
        d = DomainA()
        desc = d.describe()
        assert desc["name"] == "domain-a"
        assert desc["route_prefix"] == "/a"
        assert desc["entity_id_param"] == "a_id"
