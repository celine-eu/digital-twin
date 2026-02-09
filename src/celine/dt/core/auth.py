# celine/dt/core/auth.py
"""
Token provider factory and incoming-request JWT handling.

Uses ``celine.sdk.auth`` for:
- OIDC client-credentials flow with automatic refresh (outgoing requests).
- JWT parsing for incoming HTTP requests (``JwtUser``).
"""
from __future__ import annotations

import logging
from typing import Any

from celine.sdk.auth import (
    AccessToken,
    JwtUser,
    OidcClientCredentialsProvider,
    TokenProvider,
)

logger = logging.getLogger(__name__)

__all__ = [
    "TokenProvider",
    "AccessToken",
    "JwtUser",
    "create_token_provider",
    "parse_jwt_user",
]


async def create_token_provider(
    *,
    base_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    scope: str | None = None,
    timeout: float = 10.0,
) -> TokenProvider | None:
    """Create an OIDC client-credentials token provider.

    Returns ``None`` when ``base_url`` is empty or not provided,
    meaning authentication is disabled for this environment.
    """
    if not base_url:
        logger.info("No OIDC base_url configured — token provider disabled")
        return None

    if not client_id or not client_secret:
        logger.warning(
            "OIDC base_url set but client_id/client_secret missing — "
            "token provider disabled"
        )
        return None

    provider = OidcClientCredentialsProvider(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        timeout=timeout,
    )
    logger.info(
        "OIDC token provider created (issuer=%s, client_id=%s)",
        base_url,
        client_id,
    )
    return provider


def parse_jwt_user(
    authorization: str | None,
    *,
    verify: bool = False,
    jwks_uri: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
) -> JwtUser | None:
    """Extract a ``JwtUser`` from an incoming ``Authorization`` header.

    Args:
        authorization: Raw header value (``"Bearer <token>"``).
        verify: Whether to verify the JWT signature.
        jwks_uri: JWKS URI for signature verification.
        audience: Expected audience claim.
        issuer: Expected issuer claim.

    Returns:
        ``JwtUser`` on success, ``None`` if the header is absent or empty.

    Raises:
        ValueError: If the token is malformed or verification fails.
    """
    if not authorization:
        return None

    return JwtUser.from_token(
        authorization,
        verify=verify,
        jwks_uri=jwks_uri,
        audience=audience,
        issuer=issuer,
    )
