from __future__ import annotations
from aitbc.config.hub import hub_agent_url
from aitbc.constants import BLOCKCHAIN_RPC_URL

from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator
from pydantic_settings import SettingsConfigDict

from aitbc_shared import DatabaseConfig, ServiceSettings


class ScoreWeights(BaseModel):
    capability: float = Field(default=0.40, alias="cap")
    # not-money: a ranking weight -- these five sum to 1.00 -- not a price
    price: float = Field(default=0.20)
    latency: float = Field(default=0.20)
    trust: float = Field(default=0.15)
    load: float = Field(default=0.05)

    model_config = SettingsConfigDict(populate_by_name=True)

    def as_vector(self) -> list[float]:
        return [self.capability, self.price, self.latency, self.trust, self.load]


class Settings(ServiceSettings):
    model_config = SettingsConfigDict(env_prefix="poolhub_", env_file=".env", case_sensitive=False, extra="allow")

    app_name: str = "AITBC Pool Hub"
    bind_host: str = Field(default="127.0.0.1")
    # 8210 is the port aitbc-pool-hub.service binds and the one the port table in
    # docs/getting-started/setup-service-selection.md publishes.  This defaulted to
    # 8203, which is coordinator-api's port (V23-96).
    bind_port: int = Field(default=8210)

    coordinator_shared_secret: str = Field(
        default="",
        description="Shared secret for coordinator communication - set via POOLHUB_COORDINATOR_SHARED_SECRET env var",
    )

    # Database — uses shared DatabaseConfig with PostgreSQL adapter
    database: DatabaseConfig = Field(
        default_factory=lambda: DatabaseConfig(
            adapter="postgresql",
            url="postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc",
            pool_size=10,
        )
    )
    test_postgres_dsn: str = Field(default="postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc_test")

    @property
    def postgres_dsn(self) -> str:
        """Backward-compatible property: returns the database URL."""
        return self.database.effective_url

    @property
    def postgres_pool_min(self) -> int:
        """Backward-compatible property: returns min pool size (1)."""
        return 1

    @property
    def postgres_pool_max(self) -> int:
        """Backward-compatible property: returns max pool size from DatabaseConfig."""
        return self.database.pool_size

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
    blockchain_rpc_url: str = Field(default=BLOCKCHAIN_RPC_URL)
    default_chain_id: str = Field(default="ait-hub")

    # Agent coordinator is hub-only (V23-92). Empty means resolve from
    # HUB_AGENT_URL / HUB_DISCOVERY_URL in the node's env files.
    agent_coordinator_url: str = Field(default="")

    @model_validator(mode="after")
    def _resolve_hub_agent_url(self) -> Settings:
        if not self.agent_coordinator_url:
            resolved = hub_agent_url()
            if resolved:
                self.agent_coordinator_url = resolved
        return self

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

    # V23-101: the two intervals above configure BillingIntegrationScheduler and
    # SLACollectorScheduler, and until now nothing constructed either one -- so
    # neither field was ever read and neither loop had ever run on any deployment.
    # The schedulers are started from the app lifespan when these flags are set.
    #
    # Both default off, deliberately.  Enabling billing sync makes pool-hub POST
    # to {coordinator_billing_url}/api/billing/usage every hour, and no such route
    # exists in coordinator-api -- not in its source and not in any of the 272
    # paths of docs/api/coordinator/openapi.json -- so today it can only produce
    # hourly failures.  Enabling SLA collection starts writing sla_metrics and
    # sla_violations rows to the operator's database on a cadence they have never
    # had; that is their call to make, not a default to inherit from an upgrade.
    enable_sla_collection: bool = Field(
        default=False,
        description="Start SLACollectorScheduler at app startup (POOLHUB_ENABLE_SLA_COLLECTION=true)",
    )
    enable_billing_sync: bool = Field(
        default=False,
        description="Start BillingIntegrationScheduler at app startup (POOLHUB_ENABLE_BILLING_SYNC=true)",
    )

    def asgi_kwargs(self) -> dict[str, Any]:
        return {
            "title": self.app_name,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
