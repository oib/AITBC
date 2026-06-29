"""Trading service configuration (v0.8.0 §B1).

Provides a ``pydantic_settings.BaseSettings`` subclass with blockchain
and bridge integration fields (RPC URLs, chain_id) and inter-chain
trading parameters (matching, execution timeout, sync interval).

All fields are env-var overridable with the ``TRADING_`` prefix.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the AITBC Trading Service."""

    model_config = SettingsConfigDict(env_prefix="trading_", env_file=".env", case_sensitive=False)

    # Service bind
    bind_host: str = Field(default="0.0.0.0")
    bind_port: int = Field(default=8104)

    # Blockchain integration — port 8202 is the canonical blockchain RPC port
    blockchain_rpc_url: str = Field(default="http://localhost:8202")
    bridge_rpc_url: str = Field(default="http://localhost:8202")  # bridge is on blockchain node
    default_chain_id: str = Field(default="ait-hub")

    # Inter-chain trading parameters
    matching_enabled: bool = Field(default=True)
    execution_timeout: int = Field(default=300)  # seconds
    island_registry_sync_interval: int = Field(default=300)  # seconds

    # HTTP client timeout
    http_timeout: float = Field(default=10.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
