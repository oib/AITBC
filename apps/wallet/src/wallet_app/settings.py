from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from aitbc.constants import BLOCKCHAIN_RPC_URL, DATA_DIR
from aitbc_shared import DatabaseConfig, ServiceSettings


class Settings(ServiceSettings):
    """Runtime configuration for the wallet daemon service."""

    app_name: str = Field(default="AITBC Wallet Daemon")
    debug: bool = Field(default=False)

    coordinator_base_url: str = Field(default="http://localhost:8011", alias="COORDINATOR_BASE_URL")
    coordinator_api_key: str = Field(..., alias="COORDINATOR_API_KEY")

    # Blockchain RPC configuration for on-chain operations
    blockchain_rpc_url: str = Field(default=BLOCKCHAIN_RPC_URL, alias="BLOCKCHAIN_RPC_URL")

    rest_prefix: str = Field(default="/v1", alias="REST_PREFIX")
    # Database — uses shared DatabaseConfig with SQLite adapter
    database: DatabaseConfig = Field(default_factory=lambda: DatabaseConfig(adapter="sqlite", db_filename="wallet_ledger.db"))
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8108, alias="PORT")

    @property
    def ledger_db_path(self) -> Path:
        """Backward-compatible property: returns the ledger DB path as a Path."""
        url = self.database.effective_url
        # effective_url returns "sqlite:///path/to/db" — extract the path
        if url.startswith("sqlite:///"):
            return Path(url.removeprefix("sqlite:///"))
        return DATA_DIR / "data" / "wallet_ledger.db"

    @field_validator("coordinator_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if v.startswith("$") or not v or v == "your_api_key_here":
            raise ValueError("COORDINATOR_API_KEY must be set to a valid value and cannot be a template placeholder")
        return v

    @field_validator("blockchain_rpc_url")
    @classmethod
    def validate_blockchain_rpc_url(cls, v: str) -> str:
        if "localhost" in v or "127.0.0.1" in v:
            env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "dev"))
            if env == "production":
                raise ValueError("BLOCKCHAIN_RPC_URL cannot be localhost in production")
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
