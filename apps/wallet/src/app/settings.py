from __future__ import annotations

import os
from pathlib import Path

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

from aitbc.constants import DATA_DIR


class Settings(BaseSettings):
    """Runtime configuration for the wallet daemon service."""

    app_name: str = Field(default="AITBC Wallet Daemon")
    debug: bool = Field(default=False)

    coordinator_base_url: str = Field(default="http://localhost:8011", alias="COORDINATOR_BASE_URL")
    coordinator_api_key: str = Field(..., alias="COORDINATOR_API_KEY")

    # Blockchain RPC configuration for on-chain operations
    blockchain_rpc_url: str = Field(default="http://localhost:8202", alias="BLOCKCHAIN_RPC_URL")

    rest_prefix: str = Field(default="/v1", alias="REST_PREFIX")
    ledger_db_path: Path = Field(default=DATA_DIR / "data" / "wallet_ledger.db", alias="LEDGER_DB_PATH")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8108, alias="PORT")

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

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
