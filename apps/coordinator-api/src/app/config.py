"""
Unified configuration for AITBC Coordinator API

Provides environment-based adapter selection and consolidated settings.
"""

import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path
import secrets
import string


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

        # Default SQLite path - consistent with blockchain-node pattern
        if self.adapter == "sqlite":
            return "sqlite:////var/lib/aitbc/data/coordinator.db"

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
    
    # Database Connection Pooling
    db_pool_size: int = Field(default=20, description="Database connection pool size")
    db_max_overflow: int = Field(default=40, description="Maximum overflow connections")
    db_pool_recycle: int = Field(default=3600, description="Connection recycle time in seconds")
    db_pool_pre_ping: bool = Field(default=True, description="Test connections before using")
    db_echo: bool = Field(default=False, description="Enable SQL query logging")

    # API Keys
    client_api_keys: List[str] = []
    miner_api_keys: List[str] = []
    admin_api_keys: List[str] = []

    @field_validator('client_api_keys', 'miner_api_keys', 'admin_api_keys')
    @classmethod
    def validate_api_keys(cls, v: List[str]) -> List[str]:
        # Allow empty API keys in development/test environments
        import os
        if os.getenv('APP_ENV', 'dev') != 'production' and not v:
            return v
        if not v:
            raise ValueError('API keys cannot be empty in production')
        for key in v:
            if not key or key.startswith('$') or key == 'your_api_key_here':
                raise ValueError('API keys must be set to valid values')
            if len(key) < 16:
                raise ValueError('API keys must be at least 16 characters long')
        return v

    # Security
    hmac_secret: Optional[str] = None
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    @field_validator('hmac_secret')
    @classmethod
    def validate_hmac_secret(cls, v: Optional[str]) -> Optional[str]:
        # Allow None in development/test environments
        import os
        if os.getenv('APP_ENV', 'dev') != 'production' and not v:
            return v
        if not v or v.startswith('$') or v == 'your_secret_here':
            raise ValueError('HMAC_SECRET must be set to a secure value')
        if len(v) < 32:
            raise ValueError('HMAC_SECRET must be at least 32 characters long')
        return v

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v: Optional[str]) -> Optional[str]:
        # Allow None in development/test environments
        import os
        if os.getenv('APP_ENV', 'dev') != 'production' and not v:
            return v
        if not v or v.startswith('$') or v == 'your_secret_here':
            raise ValueError('JWT_SECRET must be set to a secure value')
        if len(v) < 32:
            raise ValueError('JWT_SECRET must be at least 32 characters long')
        return v

    # CORS
    allow_origins: List[str] = [
        "http://localhost:8000",  # Coordinator API
        "http://localhost:8001",  # Exchange API
        "http://localhost:8002",  # Blockchain Node
        "http://localhost:8003",  # Blockchain RPC
        "http://localhost:8010",  # Multimodal GPU
        "http://localhost:8011",  # GPU Multimodal
        "http://localhost:8012",  # Modality Optimization
        "http://localhost:8013",  # Adaptive Learning
        "http://localhost:8014",  # Marketplace Enhanced
        "http://localhost:8015",  # OpenClaw Enhanced
        "http://localhost:8016",  # Web UI
    ]

    # Job Configuration
    job_ttl_seconds: int = 900
    heartbeat_interval_seconds: int = 10
    heartbeat_timeout_seconds: int = 30

    # Rate Limiting
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Configurable Rate Limits (per minute)
    rate_limit_jobs_submit: str = "100/minute"
    rate_limit_miner_register: str = "30/minute"
    rate_limit_miner_heartbeat: str = "60/minute"
    rate_limit_admin_stats: str = "20/minute"
    rate_limit_marketplace_list: str = "100/minute"
    rate_limit_marketplace_stats: str = "50/minute"
    rate_limit_marketplace_bid: str = "30/minute"
    rate_limit_exchange_payment: str = "20/minute"

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
        # Default SQLite path - consistent with blockchain-node pattern
        return "sqlite:////var/lib/aitbc/data/coordinator.db"

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
