# tests/conftest.py
from celine.dt.core.datasets.client import DatasetClient


class FakeDatasetClient(DatasetClient):
    async def query(self, dataset_id: str, **_):
        if dataset_id == "silver.energy.demand":
            return [{"value": 5}, {"value": 5}]
        if dataset_id == "silver.energy.production":
            return [{"value": 10}, {"value": 10}]
        return []

    def stream(self, dataset_id: str, **_):
        async def gen():
            if dataset_id == "silver.energy.demand":
                yield [{"value": 5}, {"value": 5}]
            if dataset_id == "silver.energy.production":
                yield [{"value": 10}, {"value": 10}]

        return gen()

    async def metadata(self, dataset_id: str):
        return {"id": dataset_id}
