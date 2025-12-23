from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Central configuration (env + yaml driven)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    app_env: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    # Allow glob patterns: e.g. config/modules/*.yaml
    modules_config_paths: List[str] = Field(
        default_factory=lambda: ["config/modules.yaml"]
    )

    ontology_active: str = Field(default="celine")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@postgres:5432/postgres",
        description="Async SQLAlchemy database URL",
    )
    database_schema: str = Field(
        default="digital_twin",
        description="SQLAlchemy database schema",
    )
    database_pool_size: int = Field(default=10)
    database_max_overflow: int = Field(default=20)

    dataset_api_url: str = Field(
        default="http://localhost:8001",
        description="CELINE Dataset API endpoint",
    )
    dataset_api_client_id: str = Field(
        default="celine-cli",
        description="CELINE Dataset API client_id",
    )
    dataset_api_client_secret: str = Field(
        default="celine-cli",
        description="CELINE Dataset API client_secret",
    )

    oidc_token_base_url: str = Field(
        default="http://keycloak.celine.localhost",
        description="OIDC url",
    )
    oidc_client_id: str = Field(
        default="celine-cli",
        description="OIDC client_id",
    )
    oidc_client_secret: str = Field(
        default="celine-cli",
        description="OIDC  client_secret",
    )
    oidc_client_scope: str = Field(
        default="",
        description="OIDC scope",
    )

    state_store: str = Field(
        default="memory",
        description="state store",
    )


settings = Settings()
