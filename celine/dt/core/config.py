from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+psycopg://celine:celine@localhost:5432/celine_dt",
        alias="DATABASE_URL",
    )

    dataset_api_base_url: AnyUrl = Field(
        default=AnyUrl("http://localhost:8081"), alias="DATASET_API_BASE_URL"
    )
    dataset_api_token: str = Field(default="", alias="DATASET_API_TOKEN")

    default_granularity: str = Field(default="15m", alias="DEFAULT_GRANULARITY")

    apps_config_path: str = Field(
        default="./config/apps.yaml", alias="APPS_CONFIG_PATH"
    )


settings = Settings()
