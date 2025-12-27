# celine/dt/core/datasets/sql_api_client.py
from typing import AsyncIterator, Any
import httpx

from celine.dt.core.datasets.client import DatasetClient
from celine.dt.core.auth.provider import TokenProvider


class DatasetSqlApiClient(DatasetClient):
    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider | None = None,
        timeout: float = 30.0,
    ):
        self._base = base_url.rstrip("/")
        self._token_provider = token_provider
        self._timeout = timeout

    async def _headers(self) -> dict[str, str]:
        if not self._token_provider:
            return {}
        token = await self._token_provider.get_token()
        return {"Authorization": f"Bearer {token.access_token}"}

    async def query(self, dataset_id: str, *, sql=None, limit=1000, offset=0):
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._base}/dataset/{dataset_id}/query",
                params={
                    "filter": sql,
                    "limit": limit,
                    "offset": offset,
                },
                headers=await self._headers(),
            )
            r.raise_for_status()
            return r.json()["items"]

    def stream(
        self,
        dataset_id: str,
        *,
        sql=None,
        page_size: int = 1000,
    ):
        async def generator():
            offset = 0
            while True:
                batch = await self.query(
                    dataset_id,
                    sql=sql,
                    limit=page_size,
                    offset=offset,
                )
                if not batch:
                    break
                yield batch
                offset += page_size

        return generator()

    async def metadata(self, dataset_id: str):
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._base}/dataset/{dataset_id}/metadata",
                headers=await self._headers(),
            )
            r.raise_for_status()
            return r.json()
