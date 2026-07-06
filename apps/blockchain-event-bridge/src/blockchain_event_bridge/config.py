"""Configuration settings for blockchain event bridge (v0.10.7 §B5).

Subclasses ``aitbc_shared.core.config.ServiceSettings`` to inherit common
service fields (service_name, app_env, debug, log_level, database, api_prefix,
enable_metrics, enable_health_check) while adding blockchain event bridge
specific fields.
"""

import os

from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc_shared.core.config import ServiceSettings
from pydantic import ConfigDict, Field, field_validator


class Settings(ServiceSettings):
    """Configuration settings for the blockchain event bridge."""

    # Service configuration
    app_name: str = "Blockchain Event Bridge"
    # bind_host/bind_port kept for backward compat; ServiceSettings provides app_host/app_port
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8204)

    # Blockchain RPC
    blockchain_rpc_url: str = Field(default=BLOCKCHAIN_RPC_URL)

    # Gossip broker
    gossip_backend: str = Field(default="memory")  # memory, broadcast, redis
    gossip_broadcast_url: str | None = Field(default=None)

    # Coordinator API
    coordinator_api_url: str = Field(default="http://localhost:8203")
    coordinator_api_key: str | None = Field(default=None)

    # Event subscription filters
    subscribe_blocks: bool = Field(default=True)
    subscribe_transactions: bool = Field(default=True)
    subscribe_contracts: bool = Field(default=False)  # Phase 2

    # Smart contract addresses (Phase 2)
    agent_staking_address: str | None = Field(default=None)
    performance_verifier_address: str | None = Field(default=None)
    marketplace_address: str | None = Field(default=None)
    bounty_address: str | None = Field(default=None)
    bridge_address: str | None = Field(default=None)

    # Action handler enable/disable flags
    enable_agent_daemon_trigger: bool = Field(default=True)
    enable_coordinator_api_trigger: bool = Field(default=True)
    enable_marketplace_trigger: bool = Field(default=True)

    # Polling configuration (Phase 3)
    enable_polling: bool = Field(default=False)
    polling_interval_seconds: int = Field(default=60)

    @field_validator("blockchain_rpc_url")
    @classmethod
    def validate_blockchain_rpc_url(cls, v: str) -> str:
        if "localhost" in v or "127.0.0.1" in v:
            env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "dev"))
            if env == "production":
                raise ValueError("BLOCKCHAIN_RPC_URL cannot be localhost in production")
        return v

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
