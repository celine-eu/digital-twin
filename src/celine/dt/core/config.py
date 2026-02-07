# celine/dt/core/config.py
"""
Central configuration for the Digital Twin runtime.
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
    domains_config_paths: list[str] = Field(default_factory=lambda: ["config/domains.yaml"])
    clients_config_paths: list[str] = Field(default_factory=lambda: ["config/clients.yaml"])
    brokers_config_paths: list[str] = Field(default_factory=lambda: ["config/brokers.yaml"])

    # OIDC
    oidc_token_base_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_client_scope: str = ""

    # Broker
    broker_enabled: bool = True

    # Simulation workspaces
    dt_workspace_root: str = "dt_workspaces"


settings = Settings()
