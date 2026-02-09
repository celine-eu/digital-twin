# celine/dt/core/config.py
"""
Central configuration for the Digital Twin runtime.

Environment variables override defaults. OIDC and broker settings are
intentionally kept here (not in SDK settings) so the DT runtime
controls its own configuration surface.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # Config file paths (glob patterns)
    domains_config_paths: list[str] = Field(
        default_factory=lambda: ["config/domains.yaml"]
    )
    clients_config_paths: list[str] = Field(
        default_factory=lambda: ["config/clients.yaml"]
    )
    brokers_config_paths: list[str] = Field(
        default_factory=lambda: ["config/brokers.yaml"]
    )

    # OIDC — used for both outgoing (client-credentials) and incoming (JWT verify)
    oidc_token_base_url: str = Field(
        default="http://keycloak.celine.localhost/realms/celine",
        description="OIDC issuer base URL (empty to disable)",
    )
    oidc_client_id: str = Field(
        default="celine-cli",
        description="OIDC client_id",
    )
    oidc_client_secret: str = Field(
        default="celine-cli", description="OIDC client_secret"
    )
    oidc_client_scope: str = Field(default="", description="OIDC scope")

    # JWT verification for incoming requests
    oidc_jwks_uri: str = Field(
        default="",
        description="JWKS URI for incoming JWT verification (empty = unverified decode)",
    )
    oidc_verify_jwt: bool = Field(
        default=False,
        description="Whether to verify incoming JWT signatures",
    )

    # Simulation workspaces
    dt_workspace_root: str = "dt_workspaces"


settings = Settings()
