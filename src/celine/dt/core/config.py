# celine/dt/core/config.py
"""
Central configuration for the Digital Twin runtime.

Environment variables override defaults. OIDC and broker settings are
intentionally kept here (not in SDK settings) so the DT runtime
controls its own configuration surface.
"""
from __future__ import annotations

import os

# TODO: celine.sdk.posture ships in the next celine-sdk release; raise the
# celine-sdk floor in pyproject.toml to that version when it is published.
from celine.sdk.posture import PostureGuard, current_env, is_hardened
from celine.sdk.settings.models import OidcSettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "digital-twin"

# The posture signal is CELINE_ENV, then ENVIRONMENT (celine.sdk.posture), then these
# names this service read before the platform agreed on one. Only the value ``dev``
# relaxes; unset, a typo, ``test``, ``local`` or ``ci`` are all hardened.
LEGACY_ENV_VARS: tuple[str, ...] = ("APP_ENV", "ENV")


class Settings(BaseSettings):
    """Environment-driven settings with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    oidc: OidcSettings = OidcSettings(
        # From the environment when set; the local realm's identity otherwise.
        # Literal constructor arguments would override CELINE_OIDC_* and leave the
        # client unconfigurable per deployment.
        audience=os.getenv("CELINE_OIDC_AUDIENCE", "svc-digital-twin"),
        client_id=os.getenv("CELINE_OIDC_CLIENT_ID", "svc-digital-twin"),
        client_secret=os.getenv("CELINE_OIDC_CLIENT_SECRET", "svc-digital-twin"),
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
    def app_env(self) -> str:
        """The posture signal as read from the process environment; ``""`` when unset.

        Read from ``CELINE_ENV``, ``ENVIRONMENT``, ``APP_ENV`` then ``ENV``. Not a
        settings field: ``.env`` cannot relax the posture, only the process
        environment can (``task run`` exports ``CELINE_ENV=dev``).
        """
        return current_env(*LEGACY_ENV_VARS)

    @property
    def is_production(self) -> bool:
        """True unless the environment is exactly ``dev`` (unset is hardened)."""
        return is_hardened(*LEGACY_ENV_VARS)


def check_posture(settings: Settings, database_url: str | None = None) -> None:
    """Refuse to start outside dev while a development default is still in use.

    Collects every violation and raises :class:`celine.sdk.posture.InsecureConfiguration`
    (a ``RuntimeError``) once with the full list; in dev it logs one warning instead.

    * ``CELINE_OIDC_BASE_URL`` / ``CELINE_OIDC_JWKS_URI`` must be stated — the SDK
      otherwise defaults both to the local Keycloak, and incoming JWTs are verified
      against that JWKS.
    * The service secret must not be empty or equal to the client id. Only checked
      while a service identity is in use: an explicitly empty
      ``CELINE_OIDC_BASE_URL`` disables the token provider, so there is no secret
      to protect.
    * ``DATABASE_URL``, when set, must not carry a local-stack password. The runtime
      opens no database itself; the check covers domains and plugins that read it
      from the same process environment.
    """
    guard = PostureGuard(SERVICE_NAME, legacy=LEGACY_ENV_VARS)
    guard.require_explicit_oidc(settings.oidc)
    if settings.oidc.base_url:
        guard.forbid_secret_equal_to_client_id(
            "CELINE_OIDC_CLIENT_SECRET",
            settings.oidc.client_id,
            settings.oidc.client_secret,
        )
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
    guard.forbid_dev_database_url("DATABASE_URL", database_url)
    guard.enforce()


settings = Settings()
