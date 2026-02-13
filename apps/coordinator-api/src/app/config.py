from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8011

    # Use absolute path to avoid database duplicates in different working directories
    @property
    def database_url(self) -> str:
        # Find project root by looking for .git directory
        current = Path(__file__).resolve()
        while current.parent != current:
            if (current / ".git").exists():
                project_root = current
                break
            current = current.parent
        else:
            # Fallback to relative path if .git not found
            project_root = Path(__file__).resolve().parents[3]
        
        db_path = project_root / "data" / "coordinator.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    client_api_keys: List[str] = []
    miner_api_keys: List[str] = []
    admin_api_keys: List[str] = []

    hmac_secret: Optional[str] = None
    allow_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080", 
        "http://localhost:8000",
        "http://localhost:8011"
    ]

    job_ttl_seconds: int = 900
    heartbeat_interval_seconds: int = 10
    heartbeat_timeout_seconds: int = 30

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    receipt_signing_key_hex: Optional[str] = None
    receipt_attestation_key_hex: Optional[str] = None


settings = Settings()
