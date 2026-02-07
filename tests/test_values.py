# tests/test_values.py
"""
Unit tests for the values subsystem.
"""
import pytest
from typing import Any

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.values.executor import (
    FetcherDescriptor,
    ValuesFetcher,
    ValidationError,
)
from celine.dt.core.values.service import ValuesRegistry, ValuesService


class _MockClient:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.last_sql: str | None = None

    async def query(self, *, sql: str, limit: int = 100, offset: int = 0) -> list[dict]:
        self.last_sql = sql
        return self.rows[offset: offset + limit]


class TestValuesFetcher:
    @pytest.mark.asyncio
    async def test_basic_fetch(self):
        client = _MockClient(rows=[{"a": 1}])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        result = await fetcher.fetch(desc, {})
        assert result.count == 1
        assert result.items == [{"a": 1}]

    @pytest.mark.asyncio
    async def test_entity_injection(self):
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT * FROM t WHERE id = '{{ entity.id }}'",
        )
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        entity = EntityInfo(id="my-entity", domain_name="test")
        await fetcher.fetch(desc, {}, entity=entity)
        assert "my-entity" in client.last_sql

    @pytest.mark.asyncio
    async def test_validation_error(self):
        client = _MockClient()
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT 1",
            payload_schema={
                "type": "object",
                "required": ["location"],
                "properties": {"location": {"type": "string"}},
            },
        )
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        with pytest.raises(ValidationError):
            await fetcher.fetch(desc, {})

    @pytest.mark.asyncio
    async def test_defaults_applied(self):
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT * WHERE status = :status",
            payload_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "default": "active"},
                },
            },
        )
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        await fetcher.fetch(desc, {})
        assert "'active'" in client.last_sql

    @pytest.mark.asyncio
    async def test_limit_offset_override(self):
        rows = [{"i": i} for i in range(10)]
        client = _MockClient(rows=rows)
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1", limit=100)
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        result = await fetcher.fetch(desc, {}, limit=3, offset=2)
        assert result.count == 3
        assert result.limit == 3
        assert result.offset == 2

    @pytest.mark.asyncio
    async def test_metadata_in_jinja(self):
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query=(
                "SELECT * FROM t"
                "{% if entity and entity.metadata.zone %}"
                " WHERE zone = '{{ entity.metadata.zone }}'"
                "{% endif %}"
            ),
        )
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        entity = EntityInfo(id="x", domain_name="test", metadata={"zone": "NORD"})
        await fetcher.fetch(desc, {}, entity=entity)
        assert "NORD" in client.last_sql


class TestValuesRegistry:
    def test_register_and_get(self):
        reg = ValuesRegistry()
        spec = ValueFetcherSpec(id="my-val", client="mock")
        reg.register(FetcherDescriptor(spec=spec, client=_MockClient()))
        assert reg.has("my-val")
        d = reg.get("my-val")
        assert d.id == "my-val"

    def test_duplicate_raises(self):
        reg = ValuesRegistry()
        spec = ValueFetcherSpec(id="dup", client="mock")
        reg.register(FetcherDescriptor(spec=spec, client=_MockClient()))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(FetcherDescriptor(spec=spec, client=_MockClient()))

    def test_missing_raises(self):
        reg = ValuesRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nope")


class TestValuesService:
    @pytest.mark.asyncio
    async def test_fetch_delegates(self):
        client = _MockClient(rows=[{"val": 10}])
        registry = ValuesRegistry()
        spec = ValueFetcherSpec(id="ns.test", client="mock", query="SELECT 1")
        registry.register(FetcherDescriptor(spec=spec, client=client))
        service = ValuesService(registry=registry, fetcher=ValuesFetcher())
        result = await service.fetch(fetcher_id="ns.test", payload={})
        assert result.count == 1

    def test_list(self):
        registry = ValuesRegistry()
        spec = ValueFetcherSpec(id="a", client="mock")
        registry.register(FetcherDescriptor(spec=spec, client=_MockClient()))
        service = ValuesService(registry=registry, fetcher=ValuesFetcher())
        listed = service.list()
        assert len(listed) == 1
        assert listed[0]["id"] == "a"

    @pytest.mark.asyncio
    async def test_entity_passed_through(self):
        client = _MockClient(rows=[])
        registry = ValuesRegistry()
        spec = ValueFetcherSpec(
            id="ns.ent",
            client="mock",
            query="SELECT * FROM t WHERE id = '{{ entity.id }}'",
        )
        registry.register(FetcherDescriptor(spec=spec, client=client))
        service = ValuesService(registry=registry, fetcher=ValuesFetcher())
        entity = EntityInfo(id="e-42", domain_name="test")
        await service.fetch(fetcher_id="ns.ent", payload={}, entity=entity)
        assert "e-42" in client.last_sql
