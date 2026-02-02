# tests/core/auth/test_dataset_client_auth.py
import pytest
import httpx

from celine.dt.core.datasets.dataset_api import DatasetSqlApiClient
from celine.sdk.auth.models import AccessToken
from celine.sdk.auth.provider import TokenProvider


class FakeTokenProvider(TokenProvider):
    async def get_token(self):
        return AccessToken("abc123", expires_at=999999999)


@pytest.mark.asyncio
async def test_dataset_client_adds_bearer_token(monkeypatch):
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer abc123"
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )

    client = DatasetSqlApiClient(
        base_url="http://dataset",
        token_provider=FakeTokenProvider(),
    )

    result = await client.query(sql="SELECT 1")
    assert result == []
