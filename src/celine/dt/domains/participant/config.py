from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ParticipantDomainSettings(BaseSettings):
    """Settings for participant domain with REC Registry integration."""

    model_config = SettingsConfigDict(
        env_prefix="PARTICIPANT_",  # Looks for PARTICIPANT_* env vars
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    registry_base_url: str = Field(
        default="http://api.celine.localhost/rec-registry",
        description="REC Registry API base URL",
    )

    registry_timeout: float = Field(
        default=10.0,
        description="Registry API request timeout in seconds",
    )
