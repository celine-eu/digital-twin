# tests/unit/adapters/test_sql_api_adapter.py
import pandas as pd
import pytest

from celine.dt.adapters.sql_api import DatasetSqlApiClient


class FakeClient(DatasetSqlApiClient):
    async def query(self, sql, params):
        return [{"a": 1}, {"a": 2}]


@pytest.mark.asyncio
async def test_sql_api_adapter():
    from celine.dt.adapters.sql_api import DatasetSqlApiAdapter

    adapter = DatasetSqlApiAdapter(client=FakeClient(base_url=""))
    df = await adapter.query("select 1", {})

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
