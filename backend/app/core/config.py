"""Application configuration loaded from environment variables / .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/ directory (this file lives at backend/app/core/config.py)
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed settings. Values come from the environment or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Intelligent Code Review & Security Vulnerability Detection"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Leave empty to use the default SQLite file at backend/data/codeshield.db
    database_url: str = ""

    # Stored as a comma-separated string so it is easy to set in a .env file.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- AI layer (provider-independent) ---
    # auto | anthropic | openai_compatible | none. "auto" uses whichever API key is set.
    ai_provider: str = "auto"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    openai_max_tokens_param: str = "max_tokens"
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    ai_max_input_chars: int = 24000
    ai_max_output_tokens: int = 3000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, usable as a FastAPI dependency."""
    return Settings()
