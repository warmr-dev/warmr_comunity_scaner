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
    database_url: str = "sqlite:///./data/scanner.db"
    redis_url: str = "redis://localhost:6379/0"
    use_fetch_queue: bool = False

    searxng_base_url: str = "http://127.0.0.1:8080"
    # Global web discovery via self-hosted SearXNG only.
    discovery_providers: str = "searxng"
    discovery_concurrency: int = Field(default=2, ge=1, le=50)
    brave_search_api_key: str = ""

    llm_enabled: bool = False
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    warmr_database_url: str = ""
    warmr_sync_enabled: bool = False
    sync_value_tiers: str = "high,medium,low"
    warmr_table_name: str = "community_scanner"
    warmr_upsert_key: str = "canonical_key"

    http_timeout_seconds: float = 12.0
    crawl_download_delay_seconds: float = 0.0
    fetch_concurrency: int = Field(default=50, ge=1, le=500)
    fetch_batch_size: int = Field(default=500, ge=1, le=10_000)
    worker_max_items: int = Field(default=100_000, ge=1, le=5_000_000)
    fetch_queue_key: str = "scanner:fetch_queue"

    # Discovery scope (USA-only by default).
    pipe_geo: str = "USA"
    pipe_niche: str = "business"
    pipe_audience: str = "professionals"
    searxng_language: str = "en-US"

    @property
    def discovery_provider_list(self) -> list[str]:
        return [p.strip() for p in self.discovery_providers.split(",") if p.strip()]

    @property
    def sync_value_tier_list(self) -> list[str]:
        return [t.strip() for t in self.sync_value_tiers.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
