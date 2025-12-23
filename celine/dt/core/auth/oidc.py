# celine/dt/core/auth/oidc.py
import time
import httpx

from celine.dt.core.auth.models import AccessToken
from celine.dt.core.auth.provider import TokenProvider
from celine.dt.core.auth.oidc_discovery import OidcDiscoveryClient


class OidcClientCredentialsProvider(TokenProvider):
    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        timeout: float = 10.0,
    ):
        self._discovery = OidcDiscoveryClient(base_url, timeout)
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._timeout = timeout

        self._token: AccessToken | None = None

    async def get_token(self) -> AccessToken:
        if self._token and self._token.is_valid():
            return self._token

        if self._token and self._token.refresh_token:
            try:
                self._token = await self._refresh(self._token.refresh_token)
                return self._token
            except Exception:
                pass

        self._token = await self._authenticate()
        return self._token

    async def _authenticate(self) -> AccessToken:
        cfg = await self._discovery.get_config()

        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            data["scope"] = self._scope

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(cfg.token_endpoint, data=data)
            r.raise_for_status()
            payload = r.json()

        return self._parse_token(payload)

    async def _refresh(self, refresh_token: str) -> AccessToken:
        cfg = await self._discovery.get_config()

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(cfg.token_endpoint, data=data)
            r.raise_for_status()
            payload = r.json()

        return self._parse_token(payload)

    def _parse_token(self, payload: dict) -> AccessToken:
        now = time.time()
        return AccessToken(
            access_token=payload["access_token"],
            expires_at=now + payload.get("expires_in", 300),
            refresh_token=payload.get("refresh_token"),
        )
