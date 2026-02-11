from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the wallet daemon service."""

    app_name: str = Field(default="AITBC Wallet Daemon")
    debug: bool = Field(default=False)

    coordinator_base_url: str = Field(default="http://localhost:8011", alias="COORDINATOR_BASE_URL")
    coordinator_api_key: str = Field(default="${CLIENT_API_KEY}", alias="COORDINATOR_API_KEY")

    rest_prefix: str = Field(default="/v1", alias="REST_PREFIX")
    ledger_db_path: Path = Field(default=Path("./data/wallet_ledger.db"), alias="LEDGER_DB_PATH")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
