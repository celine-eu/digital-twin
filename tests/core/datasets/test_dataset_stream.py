import pytest

from celine.dt.core.datasets.dataset_api import DatasetSqlApiClient


@pytest.mark.asyncio
async def test_dataset_stream_paginates(monkeypatch):
    calls = []

    async def fake_query(self, dataset_id, *, filter=None, limit=1000, offset=0):
        calls.append(offset)
        if offset >= 2:
            return []
        return [{"x": offset}]

    client = DatasetSqlApiClient(base_url="http://dataset")
    monkeypatch.setattr(client, "query", fake_query.__get__(client))

    items = []
    async for batch in client.stream("ds1", page_size=1):
        items.extend(batch)

    assert items == [{"x": 0}, {"x": 1}]
    assert calls == [0, 1, 2]
