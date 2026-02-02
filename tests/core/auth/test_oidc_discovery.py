# tests/core/auth/test_oidc_discovery.py
import pytest
import httpx

from celine.sdk.auth.oidc_discovery import OidcDiscoveryClient


@pytest.mark.asyncio
async def test_oidc_discovery_loads_well_known(monkeypatch):
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "issuer": "http://issuer",
                "token_endpoint": "http://issuer/token",
                "jwks_uri": "http://issuer/jwks",
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )

    client = OidcDiscoveryClient("http://issuer")
    cfg = await client.get_config()

    assert cfg.issuer == "http://issuer"
    assert cfg.token_endpoint == "http://issuer/token"
    assert cfg.jwks_uri == "http://issuer/jwks"
