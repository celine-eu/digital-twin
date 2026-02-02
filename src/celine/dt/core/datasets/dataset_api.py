from typing import Any, AsyncIterator
import httpx

from celine.dt.core.datasets.client import DatasetClient
from celine.sdk.auth.provider import TokenProvider


from typing import Any, AsyncIterator
import httpx

from celine.dt.core.datasets.client import DatasetClient
from celine.sdk.auth.provider import TokenProvider


class DatasetSqlApiClient(DatasetClient):
    """
    Thin client for the CELINE Dataset SQL API.

    Contract:
      POST /query
      body: { sql: str, offset: int, limit: int }
    """

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

    async def query(
        self,
        *,
        sql: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base}/query",
                json={
                    "sql": sql,
                    "limit": limit,
                    "offset": offset,
                },
                headers=await self._headers(),
            )
            r.raise_for_status()
            return r.json()["items"]

    def stream(
        self,
        *,
        sql: str,
        page_size: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        async def generator():
            offset = 0
            while True:
                batch = await self.query(
                    sql=sql,
                    limit=page_size,
                    offset=offset,
                )
                if not batch:
                    break
                yield batch
                offset += page_size

        return generator()
