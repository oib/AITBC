"""Configuration for AITBC Marketplace Service (v0.6.6)."""

from __future__ import annotations

import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseSettings  # type: ignore[assignment]

    SettingsConfigDict = None  # type: ignore[misc,assignment]


class Settings(BaseSettings):
    """Marketplace service settings (v0.6.6)."""

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # Blockchain integration
    blockchain_rpc_url: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    default_chain_id: str = os.getenv("DEFAULT_CHAIN_ID", "ait-hub")

    # Agent coordinator integration (v0.6.6 matching → task queue)
    agent_coordinator_url: str = os.getenv("AGENT_COORDINATOR_URL", "http://localhost:8107")

    # Service binding
    marketplace_bind_host: str = os.getenv("MARKETPLACE_BIND_HOST", "0.0.0.0")  # nosec B104
    marketplace_bind_port: int = int(os.getenv("MARKETPLACE_BIND_PORT", "8102"))

    if SettingsConfigDict is None:

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False
            extra = "allow"


settings = Settings()
