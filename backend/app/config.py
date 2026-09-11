from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "MLB Defense API"
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://mlb:mlb@localhost:5432/mlbdefense"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_spray: int = 86_400       # 24 hours — spray profiles change nightly
    cache_ttl_alignment: int = 3_600    # 1 hour  — alignment responses

    # External APIs
    mlb_stats_api_base: str = "https://statsapi.mlb.com/api/v1"
    open_meteo_base: str = "https://api.open-meteo.com/v1"

    # Workers
    worker_enabled: bool = True

    # Public exposure (e.g. Cloudflare tunnel): block mutation endpoints
    # (ingest triggers, injury edits) so visitors can only read + compute
    public_mode: bool = False

    # Alignment engine
    alignment_min_spray_sample: int = 30   # min pitches to trust a spray profile
    alignment_grid_size: int = 100         # coverage map resolution (100×100)
    alignment_top_n: int = 3               # number of alternatives to return

    # Spray aggregation
    # Per-year multiplicative decay applied to the season=0 "Total" spray chart
    # so recent seasons weigh more heavily (hitter tendencies drift over time,
    # esp. across the 2023 shift-rule change). A season N years before the most
    # recent one contributes spray_recency_decay ** N. 1.0 disables recency bias
    # (straight sample-weighted average). 0.72 ≈ a 2-year half-life.
    spray_recency_decay: float = 0.72

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
