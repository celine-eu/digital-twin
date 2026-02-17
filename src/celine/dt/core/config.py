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

from celine.sdk.settings.models import OidcSettings


class Settings(BaseSettings):
    """Environment-driven settings with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    oidc: OidcSettings = OidcSettings(
        audience="svc-digital-twin",
        client_id="svc-digital-twin",
        client_secret="svc-digital-twin",
    )

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

    # Simulation workspaces
    dt_workspace_root: str = "dt_workspaces"


settings = Settings()
