# celine/dt/core/auth/oidc_discovery.py
import httpx

from celine.dt.core.auth.oidc_models import OidcConfiguration


class OidcDiscoveryClient:
    def __init__(self, issuer_base_url: str, timeout: float = 10.0):
        self._issuer = issuer_base_url.rstrip("/")
        self._timeout = timeout
        self._config: OidcConfiguration | None = None

    async def get_config(self) -> OidcConfiguration:
        if self._config:
            return self._config

        url = f"{self._issuer}/.well-known/openid-configuration"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()

        self._config = OidcConfiguration(
            issuer=payload["issuer"],
            token_endpoint=payload["token_endpoint"],
            jwks_uri=payload["jwks_uri"],
        )
        return self._config
