from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8011

    database_url: str = "sqlite:///./coordinator.db"

    client_api_keys: List[str] = ["REDACTED_CLIENT_KEY"]
    miner_api_keys: List[str] = ["REDACTED_MINER_KEY"]
    admin_api_keys: List[str] = ["REDACTED_ADMIN_KEY"]

    hmac_secret: Optional[str] = None
    allow_origins: List[str] = ["*"]

    job_ttl_seconds: int = 900
    heartbeat_interval_seconds: int = 10
    heartbeat_timeout_seconds: int = 30

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    receipt_signing_key_hex: Optional[str] = None
    receipt_attestation_key_hex: Optional[str] = None


settings = Settings()
