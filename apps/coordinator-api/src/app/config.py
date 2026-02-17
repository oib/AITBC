"""
Unified configuration for AITBC Coordinator API

Provides environment-based adapter selection and consolidated settings.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path


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

        # Default SQLite path
        if self.adapter == "sqlite":
            return "sqlite:///./coordinator.db"

        # Default PostgreSQL connection string
        return f"{self.adapter}://localhost:5432/coordinator"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class Settings(BaseSettings):
    """Unified application settings with environment-based configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )

    # Environment
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8011
    audit_log_dir: str = "/var/log/aitbc/audit"

    # Database
    database: DatabaseConfig = DatabaseConfig()

    # API Keys
    client_api_keys: List[str] = []
    miner_api_keys: List[str] = []
    admin_api_keys: List[str] = []

    # Security
    hmac_secret: Optional[str] = None
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # CORS
    allow_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000",
        "http://localhost:8011",
    ]

    # Job Configuration
    job_ttl_seconds: int = 900
    heartbeat_interval_seconds: int = 10
    heartbeat_timeout_seconds: int = 30

    # Rate Limiting
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Receipt Signing
    receipt_signing_key_hex: Optional[str] = None
    receipt_attestation_key_hex: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Mempool
    mempool_backend: str = "database"  # database, memory

    # Blockchain RPC
    blockchain_rpc_url: str = "http://localhost:8082"

    # Test Configuration
    test_mode: bool = False
    test_database_url: Optional[str] = None

    def validate_secrets(self) -> None:
        """Validate that all required secrets are provided."""
        if self.app_env == "production":
            if not self.jwt_secret:
                raise ValueError(
                    "JWT_SECRET environment variable is required in production"
                )
            if self.jwt_secret == "change-me-in-production":
                raise ValueError("JWT_SECRET must be changed from default value")

    @property
    def database_url(self) -> str:
        """Get the database URL (backward compatibility)."""
        # Use test database if in test mode and test_database_url is set
        if self.test_mode and self.test_database_url:
            return self.test_database_url
        if self.database.url:
            return self.database.url
        # Default SQLite path for backward compatibility
        return f"sqlite:///./aitbc_coordinator.db"

    @database_url.setter
    def database_url(self, value: str):
        """Allow setting database URL for tests"""
        if not self.test_mode:
            raise RuntimeError("Cannot set database_url outside of test mode")
        self.test_database_url = value


settings = Settings()

# Enable test mode if environment variable is set
if os.getenv("TEST_MODE") == "true":
    settings.test_mode = True
    if os.getenv("TEST_DATABASE_URL"):
        settings.test_database_url = os.getenv("TEST_DATABASE_URL")

# Validate secrets on import
settings.validate_secrets()
