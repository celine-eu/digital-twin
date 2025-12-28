# tests/conftest.py
from celine.dt.core.datasets.client import DatasetClient


class FakeDatasetClient(DatasetClient):
    async def query(self, *, sql: str, **_):
        if "energy.demand" in sql:
            return [{"value": 5}, {"value": 5}]
        if "energy.production" in sql:
            return [{"value": 10}, {"value": 10}]
        return []

    def stream(self, *, sql: str, **_):
        async def gen():
            yield await self.query(sql=sql)

        return gen()
