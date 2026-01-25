# celine/dt/core/config.py
"""
Central configuration for the Digital Twin runtime.

This module provides settings for all DT subsystems including
brokers, subscriptions, values, and clients.
"""
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

    # -------------------------------------------------------------------------
    # Config file paths (support glob patterns)
    # -------------------------------------------------------------------------
    modules_config_paths: List[str] = Field(
        default_factory=lambda: ["config/modules.yaml"],
        description="Glob patterns for module config files",
    )

    clients_config_paths: List[str] = Field(
        default_factory=lambda: ["config/clients.yaml"],
        description="Glob patterns for client config files",
    )

    values_config_paths: List[str] = Field(
        default_factory=lambda: ["config/values.yaml"],
        description="Glob patterns for values config files",
    )

    brokers_config_paths: List[str] = Field(
        default_factory=lambda: ["config/brokers.yaml"],
        description="Glob patterns for broker config files",
    )

    subscriptions_config_paths: List[str] = Field(
        default_factory=lambda: ["config/subscriptions.yaml"],
        description="Glob patterns for subscription config files",
    )

    # -------------------------------------------------------------------------
    # Ontology
    # -------------------------------------------------------------------------
    ontology_active: str = Field(default="celine")

    # -------------------------------------------------------------------------
    # Database (for DT state, not datasets)
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # OIDC (token provider for authenticated clients)
    # -------------------------------------------------------------------------
    oidc_token_base_url: str = Field(
        default="",
        description="OIDC issuer URL (empty to disable)",
    )
    oidc_client_id: str = Field(
        default="",
        description="OIDC client_id",
    )
    oidc_client_secret: str = Field(
        default="",
        description="OIDC client_secret",
    )
    oidc_client_scope: str = Field(
        default="dataset.query",
        description="OIDC scope",
    )

    # -------------------------------------------------------------------------
    # State store
    # -------------------------------------------------------------------------
    state_store: str = Field(
        default="memory",
        description="State store type (memory, ...)",
    )

    # -------------------------------------------------------------------------
    # Broker settings (publishing)
    # -------------------------------------------------------------------------
    broker_enabled: bool = Field(
        default=True,
        description="Whether to enable event broker publishing",
    )

    broker_publish_app_events: bool = Field(
        default=True,
        description="Publish app execution events (started, completed, failed)",
    )

    broker_publish_computed_events: bool = Field(
        default=True,
        description="Publish computed result events from apps",
    )

    # -------------------------------------------------------------------------
    # Subscription settings (receiving)
    # -------------------------------------------------------------------------
    subscriptions_enabled: bool = Field(
        default=True,
        description="Whether to enable event subscriptions",
    )

    subscriptions_max_concurrent: int = Field(
        default=100,
        description="Maximum concurrent handler invocations",
    )


settings = Settings()
