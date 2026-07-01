from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoreWeights(BaseModel):
    capability: float = Field(default=0.40, alias="cap")
    price: float = Field(default=0.20)
    latency: float = Field(default=0.20)
    trust: float = Field(default=0.15)
    load: float = Field(default=0.05)

    model_config = SettingsConfigDict(populate_by_name=True)

    def as_vector(self) -> list[float]:
        return [self.capability, self.price, self.latency, self.trust, self.load]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="poolhub_", env_file=".env", case_sensitive=False)

    app_name: str = "AITBC Pool Hub"
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8203)

    coordinator_shared_secret: str = Field(
        default="",
        description="Shared secret for coordinator communication - set via POOLHUB_COORDINATOR_SHARED_SECRET env var",
    )

    postgres_dsn: str = Field(default="postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc")
    postgres_pool_min: int = Field(default=1)
    postgres_pool_max: int = Field(default=10)
    test_postgres_dsn: str = Field(default="postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc_test")

    redis_url: str = Field(default="redis://127.0.0.1:6379/4")
    redis_max_connections: int = Field(default=32)
    test_redis_url: str = Field(default="redis://127.0.0.1:6379/4")

    session_ttl_seconds: int = Field(default=60)
    heartbeat_grace_seconds: int = Field(default=120)

    default_score_weights: ScoreWeights = Field(default_factory=ScoreWeights)

    allowed_origins: list[AnyHttpUrl] = Field(default_factory=list)

    prometheus_namespace: str = Field(default="poolhub")

    # Coordinator-API Billing Integration
    coordinator_billing_url: str = Field(default="http://localhost:8011")
    coordinator_api_key: str | None = Field(default=None)

    # Blockchain integration (v0.6.7)
    blockchain_rpc_url: str = Field(default="http://localhost:8202")
    default_chain_id: str = Field(default="ait-hub")

    # Agent coordinator integration (v0.6.7 — miner registration)
    agent_coordinator_url: str = Field(default="http://localhost:8107")

    # Reward distribution (v0.6.7)
    enable_reward_distribution: bool = Field(default=False)  # feature-flagged
    reward_sync_interval_blocks: int = Field(default=100)

    # SLA Configuration
    sla_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "uptime_pct": 95.0,
            "response_time_ms": 1000.0,
            "completion_rate_pct": 90.0,
            "capacity_availability_pct": 80.0,
        }
    )

    # Capacity Planning Configuration
    capacity_forecast_hours: int = Field(default=168)
    capacity_alert_threshold_pct: float = Field(default=80.0)

    # Billing Sync Configuration
    billing_sync_interval_hours: int = Field(default=1)

    # SLA Collection Configuration
    sla_collection_interval_seconds: int = Field(default=300)

    def asgi_kwargs(self) -> dict[str, Any]:
        return {
            "title": self.app_name,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
