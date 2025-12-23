# tests/core/auth/test_oidc_token_provider.py
import pytest
import httpx
import time

from celine.dt.core.auth.oidc import OidcClientCredentialsProvider


@pytest.mark.asyncio
async def test_oidc_token_refresh(monkeypatch):
    calls = []

    async def handler(request: httpx.Request):
        path = request.url.path

        # 1️⃣ OIDC discovery
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "http://issuer",
                    "token_endpoint": "http://issuer/token",
                    "jwks_uri": "http://issuer/jwks",
                },
            )

        # 2️⃣ Token endpoint
        if path.endswith("/token"):
            calls.append("token")
            if len(calls) == 1:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "token1",
                        "expires_in": 1,
                        "refresh_token": "refresh1",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "token2",
                    "expires_in": 300,
                },
            )

        raise AssertionError(f"Unexpected URL {request.url}")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )

    provider = OidcClientCredentialsProvider(
        base_url="http://issuer",
        client_id="cid",
        client_secret="secret",
    )

    t1 = await provider.get_token()
    time.sleep(1.1)  # force expiry
    t2 = await provider.get_token()

    assert t1.access_token == "token1"
    assert t2.access_token == "token2"
    assert calls == ["token", "token"]
