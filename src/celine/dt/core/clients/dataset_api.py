# celine/dt/core/clients/dataset_api.py
"""
Thin async client for the CELINE Dataset SQL API.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from git import Optional
import httpx

logger = logging.getLogger(__name__)


class DatasetSqlApiClient:
    """HTTP client for the Dataset SQL API.

    Contract::

        POST /query
        body: { sql: str, offset: int, limit: int }
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 30.0,
        token_provider: Any | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._token_provider = token_provider

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
        token: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        headers = await self._headers()
        if token:
            headers["Authorization"] = (
                token if token.lower().startswith("bearer") else f"Bearer {token}"
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    f"{self._base}/query",
                    json={"sql": sql, "limit": limit, "offset": offset},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as ex:
                logger.warning(
                    f"Request failed status={ex.response.status_code} reason={ex.response.content}"
                )
                raise
            except Exception as e:
                logger.warning(f"Exception: {e}")
                raise

            return resp.json().get("items", [])

    async def stream(
        self,
        *,
        sql: str,
        page_size: int = 1000,
        token: Optional[str] = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        offset = 0
        while True:
            batch = await self.query(
                sql=sql, limit=page_size, offset=offset, token=token
            )
            if not batch:
                break
            yield batch
            offset += page_size
