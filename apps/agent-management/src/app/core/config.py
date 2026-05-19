"""Configuration for Agent Management Service"""

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database configuration with adapter selection."""

    adapter: str = "sqlite"  # sqlite, postgresql
    url: Optional[str] = None
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True

    @property
    def effective_url(self) -> str:
        """Get the effective database URL."""
        if self.url:
            return self.url
        if self.adapter == "sqlite":
            # Use absolute path from DATA_DIR if available
            import os
            data_dir = os.getenv("DATA_DIR", "/opt/aitbc/data")
            return f"sqlite:///{data_dir}/coordinator.db"
        return f"{self.adapter}://localhost:5432/agent_management"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class ServiceSettings(BaseSettings):
    """Base settings for AITBC microservices."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )

    # Environment
    service_name: str = "aitbc-service"
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_dir: str = "/var/log/aitbc/services"

    # Database
    database: DatabaseConfig = DatabaseConfig()

    # API
    api_prefix: str = "/v1"

    # Feature flags
    enable_metrics: bool = True
    enable_health_check: bool = True

    # API Keys (comma-separated in env)
    admin_api_keys: List[str] = Field(default_factory=list)
    client_api_keys: List[str] = Field(default_factory=list)
    miner_api_keys: List[str] = Field(default_factory=list)


# Global settings instance
settings = ServiceSettings()
