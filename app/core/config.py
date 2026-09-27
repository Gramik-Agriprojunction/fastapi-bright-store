from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bright Store API"
    app_env: str = "uat"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/bright_store"
    ai_provider: str = "none"
    ai_api_key: str | None = None
    ai_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
