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


settings = Settings()
