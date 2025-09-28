from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoreWeights(BaseModel):
    capability: float = Field(default=0.40, alias="cap")
    price: float = Field(default=0.20)
    latency: float = Field(default=0.20)
    trust: float = Field(default=0.15)
    load: float = Field(default=0.05)

    model_config = SettingsConfigDict(populate_by_name=True)

    def as_vector(self) -> List[float]:
        return [self.capability, self.price, self.latency, self.trust, self.load]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="poolhub_", env_file=".env", case_sensitive=False)

    app_name: str = "AITBC Pool Hub"
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8203)

    coordinator_shared_secret: str = Field(default="changeme")

    postgres_dsn: str = Field(default="postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc")
    postgres_pool_min: int = Field(default=1)
    postgres_pool_max: int = Field(default=10)

    redis_url: str = Field(default="redis://127.0.0.1:6379/4")
    redis_max_connections: int = Field(default=32)

    session_ttl_seconds: int = Field(default=60)
    heartbeat_grace_seconds: int = Field(default=120)

    default_score_weights: ScoreWeights = Field(default_factory=ScoreWeights)

    allowed_origins: List[AnyHttpUrl] = Field(default_factory=list)

    prometheus_namespace: str = Field(default="poolhub")

    def asgi_kwargs(self) -> Dict[str, Any]:
        return {
            "title": self.app_name,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
