"""Centraliserade settings för applikationen."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Alla settings läses från .env eller environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Databas
    database_url: str = Field(default="postgresql+psycopg://travai:travai@localhost:5432/travai")

    # ATG
    atg_base_url: str = Field(default="https://www.atg.se/services/racinginfo/v1/api")
    atg_user_agent: str = Field(default="TravAI/0.1")
    atg_rate_limit_seconds: float = Field(default=3.0)

    # Logging
    log_level: str = Field(default="INFO")


settings = Settings()
