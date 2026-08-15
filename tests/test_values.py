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
    """Stands in for ``DatasetSqlApiClient``.

    ``ctx`` is accepted because the executor threads the request context through to
    the client; a double that omits it fails with an unexpected-keyword TypeError
    rather than an assertion, which reads as a test bug and is not one.
    """

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.last_sql: str | None = None
        self.last_ctx: Any = None

    async def query(
        self,
        *,
        sql: str,
        limit: int = 100,
        offset: int = 0,
        ctx: Any = None,
    ) -> list[dict]:
        self.last_sql = sql
        self.last_ctx = ctx
        return self.rows[offset: offset + limit]


class TestValuesFetcher:
    @pytest.mark.asyncio
    # @verifies REQ-1120
    async def test_basic_fetch(self):
        client = _MockClient(rows=[{"a": 1}])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        result = await fetcher.fetch(desc, {}, ctx=None)
        assert result.count == 1
        assert result.items == [{"a": 1}]

    @pytest.mark.asyncio
    # @verifies REQ-1201
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
        await fetcher.fetch(desc, {}, entity=entity, ctx=None)
        assert "my-entity" in client.last_sql

    @pytest.mark.asyncio
    # @verifies REQ-1110
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
            await fetcher.fetch(desc, {}, ctx=None)

    @pytest.mark.asyncio
    # @verifies REQ-1111
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
        await fetcher.fetch(desc, {}, ctx=None)
        assert "'active'" in client.last_sql

    @pytest.mark.asyncio
    # @verifies REQ-1130
    # @verifies REQ-1132
    async def test_limit_offset_override(self):
        rows = [{"i": i} for i in range(10)]
        client = _MockClient(rows=rows)
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1", limit=100)
        desc = FetcherDescriptor(spec=spec, client=client)
        fetcher = ValuesFetcher()
        result = await fetcher.fetch(desc, {}, limit=3, offset=2, ctx=None)
        assert result.count == 3
        assert result.limit == 3
        assert result.offset == 2

    @pytest.mark.asyncio
    # @verifies REQ-1032
    # @verifies REQ-1201
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
        await fetcher.fetch(desc, {}, entity=entity, ctx=None)
        assert "NORD" in client.last_sql

    @pytest.mark.asyncio
    # @verifies REQ-1121
    async def test_ctx_is_threaded_through_to_the_client(self):
        """The client receives the request context.

        This is the refactor that broke the suite: `ctx` was threaded through
        executor → client and the doubles were not updated. Pinning it means the
        next such change fails on an assertion rather than on a TypeError deep in
        a mock.
        """
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        desc = FetcherDescriptor(spec=spec, client=client)
        sentinel = object()
        await ValuesFetcher().fetch(desc, {}, ctx=sentinel)
        assert client.last_ctx is sentinel

    @pytest.mark.asyncio
    # @verifies REQ-1130
    async def test_spec_limit_is_the_default(self):
        rows = [{"i": i} for i in range(10)]
        client = _MockClient(rows=rows)
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1", limit=4)
        result = await ValuesFetcher().fetch(
            FetcherDescriptor(spec=spec, client=client), {}, ctx=None
        )
        assert result.limit == 4
        assert result.count == 4

    @pytest.mark.asyncio
    # @verifies REQ-1122
    async def test_output_mapper_is_applied_to_every_row(self):
        class _Doubler:
            def map(self, item: dict) -> dict:
                return {"v": item["v"] * 2}

        client = _MockClient(rows=[{"v": 1}, {"v": 2}])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        desc = FetcherDescriptor(spec=spec, client=client, output_mapper=_Doubler())
        result = await ValuesFetcher().fetch(desc, {}, ctx=None)
        assert result.items == [{"v": 2}, {"v": 4}]
        assert result.count == 2

    @pytest.mark.asyncio
    # @verifies REQ-1123
    async def test_a_failing_output_mapper_propagates(self):
        class _Broken:
            def map(self, item: dict) -> dict:
                raise RuntimeError("mapper blew up")

        client = _MockClient(rows=[{"v": 1}])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        desc = FetcherDescriptor(spec=spec, client=client, output_mapper=_Broken())
        with pytest.raises(RuntimeError, match="mapper blew up"):
            await ValuesFetcher().fetch(desc, {}, ctx=None)

    @pytest.mark.asyncio
    # @verifies REQ-1124
    async def test_spec_without_a_query_sends_empty_sql(self):
        """A fetcher may carry no query — the client is handed `""`, not None."""
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(id="test", client="mock")
        await ValuesFetcher().fetch(
            FetcherDescriptor(spec=spec, client=client), {}, ctx=None
        )
        assert client.last_sql == ""

    @pytest.mark.asyncio
    # @verifies REQ-1112
    async def test_defaults_do_not_override_a_supplied_value(self):
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT * WHERE status = :status",
            payload_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "default": "active"}},
            },
        )
        await ValuesFetcher().fetch(
            FetcherDescriptor(spec=spec, client=client), {"status": "idle"}, ctx=None
        )
        assert "'idle'" in client.last_sql

    @pytest.mark.asyncio
    # @verifies REQ-1113
    async def test_payload_is_not_mutated(self):
        """Defaults are applied to a copy. The caller's dict is often a shared
        request payload, and mutating it leaks defaults into the next fetcher."""
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT * WHERE status = :status",
            payload_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "default": "active"}},
            },
        )
        payload: dict = {}
        await ValuesFetcher().fetch(
            FetcherDescriptor(spec=spec, client=client), payload, ctx=None
        )
        assert payload == {}

    @pytest.mark.asyncio
    # @verifies REQ-1110
    async def test_validation_error_carries_the_detail(self):
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
        with pytest.raises(ValidationError) as exc:
            await ValuesFetcher().fetch(desc, {}, ctx=None)
        body = exc.value.to_dict()
        assert body["error"] == "validation_error"
        assert body["errors"]

    @pytest.mark.asyncio
    # @verifies REQ-1110
    async def test_wrong_type_fails_validation(self):
        client = _MockClient()
        spec = ValueFetcherSpec(
            id="test",
            client="mock",
            query="SELECT 1",
            payload_schema={
                "type": "object",
                "properties": {"days": {"type": "integer"}},
            },
        )
        desc = FetcherDescriptor(spec=spec, client=client)
        with pytest.raises(ValidationError):
            await ValuesFetcher().fetch(desc, {"days": "seven"}, ctx=None)

    @pytest.mark.asyncio
    # @verifies REQ-1114
    async def test_no_schema_means_no_validation(self):
        client = _MockClient(rows=[])
        spec = ValueFetcherSpec(id="test", client="mock", query="SELECT 1")
        result = await ValuesFetcher().fetch(
            FetcherDescriptor(spec=spec, client=client), {"anything": 1}, ctx=None
        )
        assert result.count == 0


class TestValuesRegistry:
    def test_register_and_get(self):
        reg = ValuesRegistry()
        spec = ValueFetcherSpec(id="my-val", client="mock")
        reg.register(FetcherDescriptor(spec=spec, client=_MockClient()))
        assert reg.has("my-val")
        d = reg.get("my-val")
        assert d.id == "my-val"

    # @verifies REQ-1100
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
        # list() returns FetcherDescriptor objects, not dicts. The HTTP layer is what
        # turns them into JSON, via ValueDescriptorSchema.from_descriptor.
        assert listed[0].id == "a"
        assert listed[0].spec is spec

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


class TestStartupWiring:
    """`main._register_domain_values` is the step that binds specs to live clients.

    It runs in the lifespan, after clients are loaded — so its failures are startup
    failures, and this is the only place they are exercised without booting the app.
    """

    def _domain(self, client_name: str):
        from typing import ClassVar

        from celine.dt.core.domain.base import DTDomain

        class _D(DTDomain):
            name: ClassVar[str] = "wiring-test"
            domain_type: ClassVar[str] = "test"
            route_prefix: ClassVar[str] = "/wiring"
            entity_id_param: ClassVar[str] = "x_id"

            def get_value_specs(self):
                return [ValueFetcherSpec(id="v", client=client_name, query="SELECT 1")]

        return _D()

    # @verifies REQ-1101
    def test_unknown_client_fails_loudly(self):
        from celine.dt.core.clients.registry import ClientsRegistry
        from celine.dt.main import _register_domain_values

        clients = ClientsRegistry()
        clients.register("dataset_api", _MockClient())

        with pytest.raises(KeyError) as exc:
            _register_domain_values(
                self._domain("nope"), ValuesRegistry(), clients
            )
        message = str(exc.value)
        assert "nope" in message
        assert "dataset_api" in message, "the error must name what *is* available"

    # @verifies REQ-1100
    def test_specs_are_registered_namespaced(self):
        from celine.dt.core.clients.registry import ClientsRegistry
        from celine.dt.main import _register_domain_values

        clients = ClientsRegistry()
        clients.register("dataset_api", _MockClient())
        registry = ValuesRegistry()

        _register_domain_values(self._domain("dataset_api"), registry, clients)

        assert registry.has("wiring-test.v")
        assert not registry.has("v")


def test_energy_community_daily_self_consumption_fetcher_is_aggregated():
    """Large overview ranges use daily aggregation to stay under dataset limits."""
    from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain

    specs = {spec.id: spec for spec in ITEnergyCommunityDomain().get_value_specs()}
    daily = specs["rec_self_consumption_daily"]

    assert daily.limit == 370
    assert "GROUP BY CAST(ts AS date)" in daily.query
    assert "SUM(total_production_kwh)" in daily.query


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known defect: rec_self_consumption selects per-substation rows with no "
        "GROUP BY ts, so it returns 2-3 rows per timestamp and its limit=9000 covers "
        "~31 days against a 30-day window. See "
        ".agents/knowledge/rec-fetcher-row-limits.md. strict=True so this fails the "
        "suite once the fetcher is fixed, prompting the requirement to be closed."
    ),
)
# @verifies REQ-1140
def test_rec_self_consumption_aggregates_across_substations():
    """The 15-minute community fetcher must collapse the substation dimension.

    Not verifiable by watching the displayed totals: the webapp BFF sums every row it
    receives, so the numbers are already correct and do not move when this is fixed.
    """
    from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain

    specs = {s.id: s for s in ITEnergyCommunityDomain().get_value_specs()}
    query = specs["rec_self_consumption"].query

    assert "GROUP BY" in query
    assert "SUM(" in query
