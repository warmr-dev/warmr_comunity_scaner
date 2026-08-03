from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    # Local-first: SQLite. Switch to Postgres when Docker/Railway is ready.
    database_url: str = "sqlite:///./data/scanner.db"
    redis_url: str = "redis://localhost:6379/0"

    brave_search_api_key: str = ""
    searxng_base_url: str = "http://localhost:8080"
    discovery_providers: str = "seeds"

    llm_enabled: bool = False
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    warmr_database_url: str = ""
    warmr_sync_enabled: bool = False
    sync_value_tiers: str = "high,medium"

    http_timeout_seconds: float = 20.0
    crawl_download_delay_seconds: float = 1.0

    @property
    def discovery_provider_list(self) -> list[str]:
        return [p.strip() for p in self.discovery_providers.split(",") if p.strip()]

    @property
    def sync_value_tier_list(self) -> list[str]:
        return [t.strip() for t in self.sync_value_tiers.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
