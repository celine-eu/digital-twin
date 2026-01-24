# tests/core/values/test_executor.py
from __future__ import annotations

import pytest

from celine.dt.core.values.executor import ValuesFetcher, FetchResult, ValidationError
from celine.dt.core.values.registry import FetcherDescriptor
from celine.dt.core.values.config import ValueFetcherSpec


class FakeDatasetClient:
    """Fake client for testing."""

    def __init__(self):
        self.last_query = None
        self.last_limit = None
        self.last_offset = None
        self.return_value = []

    async def query(self, *, sql: str, limit: int = 100, offset: int = 0):
        self.last_query = sql
        self.last_limit = limit
        self.last_offset = offset
        return self.return_value


class FakeOutputMapper:
    """Fake output mapper for testing."""

    def map(self, item: dict) -> dict:
        return {**item, "mapped": True}


class TestValuesFetcher:
    @pytest.fixture
    def fetcher(self):
        return ValuesFetcher()

    @pytest.fixture
    def client(self):
        return FakeDatasetClient()

    def make_descriptor(
        self,
        client,
        query="SELECT * FROM table",
        payload_schema=None,
        output_mapper=None,
    ):
        spec = ValueFetcherSpec(
            id="test_fetcher",
            client="test_client",
            query=query,
            limit=100,
            payload_schema=payload_schema,
            output_mapper=None,
        )
        return FetcherDescriptor(
            spec=spec,
            client=client,
            output_mapper=output_mapper,
        )


class TestBuildQuery:
    @pytest.fixture
    def fetcher(self):
        return ValuesFetcher()

    def test_no_params(self, fetcher):
        query = fetcher.build_query("SELECT * FROM table", {})
        assert query == "SELECT * FROM table"

    def test_single_param(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM table WHERE id = :id",
            {"id": 42},
        )
        assert query == "SELECT * FROM table WHERE id = 42"

    def test_multiple_params(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE a = :a AND b = :b",
            {"a": 1, "b": 2},
        )
        assert query == "SELECT * FROM t WHERE a = 1 AND b = 2"

    def test_string_param_quoted(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE name = :name",
            {"name": "test"},
        )
        assert query == "SELECT * FROM t WHERE name = 'test'"

    def test_string_with_quote_escaped(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE name = :name",
            {"name": "it's"},
        )
        assert query == "SELECT * FROM t WHERE name = 'it''s'"

    def test_null_param(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE val = :val",
            {"val": None},
        )
        assert query == "SELECT * FROM t WHERE val = NULL"

    def test_boolean_param(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE active = :active",
            {"active": True},
        )
        assert query == "SELECT * FROM t WHERE active = TRUE"

    def test_list_param(self, fetcher):
        query = fetcher.build_query(
            "SELECT * FROM t WHERE id IN :ids",
            {"ids": [1, 2, 3]},
        )
        assert query == "SELECT * FROM t WHERE id IN (1, 2, 3)"

    def test_missing_param_raises(self, fetcher):
        with pytest.raises(ValueError, match="not provided"):
            fetcher.build_query(
                "SELECT * FROM t WHERE id = :id",
                {},
            )

    def test_none_query_returns_empty(self, fetcher):
        query = fetcher.build_query(None, {})
        assert query == ""


class TestValidatePayload:
    @pytest.fixture
    def fetcher(self):
        return ValuesFetcher()

    @pytest.fixture
    def client(self):
        return FakeDatasetClient()

    def test_no_schema_accepts_any(self, fetcher, client):
        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(id="t", client="c", payload_schema=None),
            client=client,
        )

        result = fetcher.validate_payload({"anything": "goes"}, descriptor)
        assert result == {"anything": "goes"}

    def test_valid_payload(self, fetcher, client):
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
            },
        }
        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(id="t", client="c", payload_schema=schema),
            client=client,
        )

        result = fetcher.validate_payload({"name": "test"}, descriptor)
        assert result == {"name": "test"}

    def test_applies_defaults(self, fetcher, client):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "default_name"},
            },
        }
        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(id="t", client="c", payload_schema=schema),
            client=client,
        )

        result = fetcher.validate_payload({}, descriptor)
        assert result == {"name": "default_name"}

    def test_invalid_payload_raises(self, fetcher, client):
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
            },
        }
        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(id="t", client="c", payload_schema=schema),
            client=client,
        )

        with pytest.raises(ValidationError):
            fetcher.validate_payload({}, descriptor)


class TestFetch:
    @pytest.fixture
    def fetcher(self):
        return ValuesFetcher()

    @pytest.fixture
    def client(self):
        return FakeDatasetClient()

    @pytest.mark.asyncio
    async def test_basic_fetch(self, fetcher, client):
        client.return_value = [{"id": 1}, {"id": 2}]

        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="test",
                client="c",
                query="SELECT * FROM t",
                limit=50,
            ),
            client=client,
        )

        result = await fetcher.fetch(descriptor, {})

        assert isinstance(result, FetchResult)
        assert result.items == [{"id": 1}, {"id": 2}]
        assert result.count == 2
        assert result.limit == 50
        assert result.offset == 0

    @pytest.mark.asyncio
    async def test_fetch_with_params(self, fetcher, client):
        client.return_value = [{"id": 1}]

        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="test",
                client="c",
                query="SELECT * FROM t WHERE id = :id",
            ),
            client=client,
        )

        await fetcher.fetch(descriptor, {"id": 42})

        assert "WHERE id = 42" in client.last_query

    @pytest.mark.asyncio
    async def test_fetch_override_limit_offset(self, fetcher, client):
        client.return_value = []

        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(
                id="test",
                client="c",
                query="SELECT 1",
                limit=100,
                offset=0,
            ),
            client=client,
        )

        result = await fetcher.fetch(descriptor, {}, limit=10, offset=20)

        assert client.last_limit == 10
        assert client.last_offset == 20
        assert result.limit == 10
        assert result.offset == 20

    @pytest.mark.asyncio
    async def test_fetch_with_output_mapper(self, fetcher, client):
        client.return_value = [{"id": 1}, {"id": 2}]

        descriptor = FetcherDescriptor(
            spec=ValueFetcherSpec(id="test", client="c", query="SELECT 1"),
            client=client,
            output_mapper=FakeOutputMapper(),
        )

        result = await fetcher.fetch(descriptor, {})

        assert result.items == [
            {"id": 1, "mapped": True},
            {"id": 2, "mapped": True},
        ]


class TestFetchResult:
    def test_to_dict(self):
        result = FetchResult(
            items=[{"a": 1}],
            limit=10,
            offset=5,
            count=1,
        )

        d = result.to_dict()

        assert d == {
            "items": [{"a": 1}],
            "limit": 10,
            "offset": 5,
            "count": 1,
        }
