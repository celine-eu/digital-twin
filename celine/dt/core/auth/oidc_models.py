from dataclasses import dataclass


@dataclass(frozen=True)
class OidcConfiguration:
    issuer: str
    token_endpoint: str
    jwks_uri: str
