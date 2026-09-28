# celine/dt/core/clients/dataset_api.py
"""
Thin async client for the CELINE Dataset SQL API.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator
import httpx

from celine.dt.core.clients.errors import ServiceIdentityUnavailable

if TYPE_CHECKING:
    from celine.dt.api.context import Ctx
    from celine.sdk.auth.provider import TokenProvider

logger = logging.getLogger(__name__)


def error_code(status: int) -> str:
    """A short, fixed code for a dataset-api error status, safe to log (REQ-1126).

    Derived from the status alone, never from the response body.
    """
    if status == 400:
        return "query_refused"
    if status == 401:
        return "unauthenticated"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if 400 <= status < 500:
        return "client_error"
    return "upstream_error"


def _bare(token: str) -> str:
    """``token`` without a leading ``Bearer`` scheme, in any case."""
    token = token.strip()
    scheme, _, rest = token.partition(" ")
    return rest.strip() if scheme.lower() == "bearer" and rest.strip() else token


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
        token_provider: TokenProvider | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._token_provider = token_provider

    async def _headers(self, user_token: str | None = None) -> dict[str, str]:
        """The ``Authorization`` header: the caller's token, else the service token.

        ``user_token`` is the bare token; one ``Bearer`` scheme is added here, and a
        scheme the token already carries is dropped first, so the header never reads
        ``Bearer Bearer <token>`` (REQ-1128).
        """
        token = user_token
        if not token:
            if not self._token_provider:
                return {}
            try:
                client_token = await self._token_provider.get_token()
            except Exception as e:
                # The provider is configured but cannot obtain a token (identity
                # provider down or refusing): the same coded fault as no provider, and
                # nothing is sent (REQ-1129). The exception type only: the provider's
                # message can carry its endpoint or response body.
                logger.warning(
                    "dataset-api query not sent: code=%s error=%s",
                    ServiceIdentityUnavailable.code,
                    type(e).__name__,
                )
                raise ServiceIdentityUnavailable(
                    "The Digital Twin could not obtain its service token"
                ) from e
            token = client_token.access_token

        return {"Authorization": f"Bearer {_bare(token)}"}

    async def query(
        self, *, sql: str, limit: int = 1000, offset: int = 0, ctx: Ctx | None = None
    ) -> list[dict[str, Any]]:

        # No context means the Digital Twin's own identity (REQ-1125). Without a
        # token provider there is none, and the statement is not sent unauthenticated
        # (REQ-1129).
        if ctx is None and self._token_provider is None:
            logger.warning(
                "dataset-api query not sent: code=%s", ServiceIdentityUnavailable.code
            )
            raise ServiceIdentityUnavailable()

        token: str | None = ctx.token if ctx and ctx.token else None
        headers = await self._headers(token)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    f"{self._base}/query",
                    json={"sql": sql, "limit": limit, "offset": offset, "skip_count": True},
                    headers=headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as ex:
                # Status and a fixed code only (REQ-1126). dataset-api's error body can
                # quote the statement, and a statement can carry a caller's coordinates
                # or other payload literals; the reason is in dataset-api's own log.
                status = ex.response.status_code
                logger.warning(
                    "dataset-api query failed: status=%d code=%s",
                    status,
                    error_code(status),
                )
                raise
            except Exception as e:
                logger.warning(
                    "dataset-api query failed: code=transport error=%s", type(e).__name__
                )
                raise

            return resp.json().get("items", [])

    async def stream(
        self, *, sql: str, page_size: int = 1000, ctx: Ctx | None = None
    ) -> AsyncIterator[list[dict[str, Any]]]:
        offset = 0
        while True:
            batch = await self.query(sql=sql, limit=page_size, offset=offset, ctx=ctx)
            if not batch:
                break
            yield batch
            offset += page_size
