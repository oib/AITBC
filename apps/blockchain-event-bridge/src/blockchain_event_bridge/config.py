"""Configuration settings for blockchain event bridge."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration settings for the blockchain event bridge."""

    # Service configuration
    app_name: str = "Blockchain Event Bridge"
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8204)

    # Blockchain RPC
    blockchain_rpc_url: str = Field(default="http://localhost:8006")

    # Gossip broker
    gossip_backend: str = Field(default="memory")  # memory, broadcast, redis
    gossip_broadcast_url: Optional[str] = Field(default=None)

    # Coordinator API
    coordinator_api_url: str = Field(default="http://localhost:8011")
    coordinator_api_key: Optional[str] = Field(default=None)

    # Event subscription filters
    subscribe_blocks: bool = Field(default=True)
    subscribe_transactions: bool = Field(default=True)
    subscribe_contracts: bool = Field(default=False)  # Phase 2

    # Smart contract addresses (Phase 2)
    agent_staking_address: Optional[str] = Field(default=None)
    performance_verifier_address: Optional[str] = Field(default=None)
    marketplace_address: Optional[str] = Field(default=None)
    bounty_address: Optional[str] = Field(default=None)
    bridge_address: Optional[str] = Field(default=None)

    # Action handler enable/disable flags
    enable_agent_daemon_trigger: bool = Field(default=True)
    enable_coordinator_api_trigger: bool = Field(default=True)
    enable_marketplace_trigger: bool = Field(default=True)

    # Polling configuration (Phase 3)
    enable_polling: bool = Field(default=False)
    polling_interval_seconds: int = Field(default=60)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
