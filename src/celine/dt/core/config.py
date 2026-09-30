# celine/dt/core/config.py
"""
Central configuration for the Digital Twin runtime.

Environment variables override defaults. OIDC and broker settings are
intentionally kept here (not in SDK settings) so the DT runtime
controls its own configuration surface.
"""
from __future__ import annotations

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from celine.sdk.settings.models import OidcSettings

# Values of the environment name that mean "the placeholder credentials are what I
# want". Everything else — a typo, and nothing at all — is production, so the checks
# are on unless someone opted out on purpose. Same set as celine-policies.
NON_PRODUCTION_ENVS = frozenset({"dev", "development", "local", "test", "ci"})


class Settings(BaseSettings):
    """Environment-driven settings with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    oidc: OidcSettings = OidcSettings(
        audience="svc-digital-twin",
        client_id="svc-digital-twin",
        client_secret=os.getenv("CELINE_OIDC_CLIENT_SECRET", "svc-digital-twin"),
    )

    # Read from APP_ENV, CELINE_ENV or ENV, in that order. Defaults to production so a
    # deployment that says nothing gets the strict checks.
    app_env: str = Field(
        default="prod",
        validation_alias=AliasChoices("APP_ENV", "CELINE_ENV", "ENV"),
    )
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

    # Ontology mapping spec YAMLs (relative to CWD or absolute)
    ontology_specs_dir: str = "ontologies/mapper"


    @property
    def is_production(self) -> bool:
        """True unless the environment name is a known non-production one."""
        return self.app_env.strip().lower() not in NON_PRODUCTION_ENVS


def check_service_credentials(settings: Settings) -> None:
    """Refuse to start in production with a placeholder service secret.

    A secret that is empty or equal to the client id is guessable from the client
    id alone. Only checked when client credentials are in use, i.e. an OIDC base
    URL is configured; with none there is no service identity to protect.
    """
    if not settings.is_production or not settings.oidc.base_url:
        return
    secret = settings.oidc.client_secret or ""
    if not secret or secret == settings.oidc.client_id:
        raise RuntimeError(
            f"CELINE_OIDC_CLIENT_SECRET is empty or equal to the client id "
            f"'{settings.oidc.client_id}' while APP_ENV='{settings.app_env}' is production. "
            f"Set a real secret, or set APP_ENV to one of "
            f"{sorted(NON_PRODUCTION_ENVS)} for a development environment."
        )


settings = Settings()
