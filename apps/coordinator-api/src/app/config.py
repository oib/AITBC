"""
Unified configuration for AITBC Coordinator API

Provides environment-based adapter selection and consolidated settings.
"""

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.config import BaseAITBCConfig
from aitbc.constants import DATA_DIR, LOG_DIR


class DatabaseConfig(BaseSettings):
    """Database configuration with adapter selection."""

    adapter: str = "sqlite"  # sqlite, postgresql
    url: str | None = None
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
            return f"sqlite:///{DATA_DIR}/data/coordinator.db"

        # Default PostgreSQL connection string
        return f"{self.adapter}://localhost:5432/coordinator"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")


class Settings(BaseAITBCConfig):
    """Unified application settings with environment-based configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    # Override defaults for coordinator-api
    app_name: str = Field(default="AITBC Coordinator API", description="Application name")
    app_host: str = Field(default="0.0.0.0", description="Application host")
    port: int = Field(default=8203, description="Server port")
    environment: str = Field(default="dev", description="Environment")
    audit_log_dir: str = Field(default=str(LOG_DIR / "audit"), description="Audit log directory")

    # Database
    database: DatabaseConfig = Field(default_factory=DatabaseConfig, description="Database configuration")
    db_echo: bool = Field(default=False, description="Enable SQLAlchemy query echo")
    db_pool_pre_ping: bool = Field(default=True, description="Enable connection pool pre-ping")
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Database connection pool max overflow")
    db_pool_recycle: int = Field(default=3600, description="Database connection pool recycle time in seconds")

    # API Keys
    client_api_keys: list[str] = []
    miner_api_keys: list[str] = []
    admin_api_keys: list[str] = []

    @field_validator("client_api_keys", "miner_api_keys", "admin_api_keys", mode="before")
    @classmethod
    def parse_api_keys(cls, v: str | list[str]) -> list[str]:
        import json
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            # Fall back to comma-separated
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    @field_validator("client_api_keys", "miner_api_keys", "admin_api_keys")
    @classmethod
    def validate_api_keys(cls, v: list[str]) -> list[str]:
        # Allow empty API keys in development/test environments
        import os

        if os.getenv("APP_ENV", "dev") != "production" and not v:
            return v
        if not v:
            raise ValueError("API keys cannot be empty in production")
        for key in v:
            if not key or key.startswith("$") or key == "your_api_key_here":
                raise ValueError("API keys must be set to valid values")
            if len(key) < 16:
                raise ValueError("API keys must be at least 16 characters long")
        return v

    # Security - using inherited secret_key and jwt_secret from BaseAITBCConfig
    hmac_secret: str | None = None

    # CORS - override inherited allow_origins with coordinator-api specific defaults
    allow_origins: list[str] = Field(
        default=[
            "http://localhost:8203",  # Coordinator API
            "http://localhost:8001",  # Exchange API
            "http://localhost:8002",  # Blockchain Node
            "http://localhost:8003",  # Blockchain RPC
            "http://localhost:8010",  # Multimodal GPU
            "http://localhost:8011",  # GPU Multimodal
            "http://localhost:8012",  # Modality Optimization
            "http://localhost:8013",  # Adaptive Learning
            "http://localhost:8014",  # Marketplace Enhanced
            "http://localhost:8015",  # hermes Enhanced
            "http://localhost:8016",  # Web UI
        ],
        description="CORS allowed origins"
    )

    # Job Configuration
    job_ttl_seconds: int = Field(default=900, description="Job TTL in seconds")
    heartbeat_interval_seconds: int = Field(default=10, description="Heartbeat interval in seconds")
    heartbeat_timeout_seconds: int = Field(default=30, description="Heartbeat timeout in seconds")

    # Configurable Rate Limits (per minute) - extending inherited rate limiting
    rate_limit_jobs_submit: str = Field(default="100/minute", description="Rate limit for job submission")
    rate_limit_miner_register: str = Field(default="30/minute", description="Rate limit for miner registration")
    rate_limit_miner_heartbeat: str = Field(default="60/minute", description="Rate limit for miner heartbeat")
    rate_limit_admin_stats: str = Field(default="20/minute", description="Rate limit for admin stats")
    rate_limit_marketplace_list: str = Field(default="100/minute", description="Rate limit for marketplace list")
    rate_limit_marketplace_stats: str = Field(default="50/minute", description="Rate limit for marketplace stats")
    rate_limit_marketplace_bid: str = Field(default="30/minute", description="Rate limit for marketplace bid")
    rate_limit_exchange_payment: str = Field(default="20/minute", description="Rate limit for exchange payment")

    # Receipt Signing
    receipt_signing_key_hex: str | None = None
    receipt_attestation_key_hex: str | None = None

    # Logging - using inherited log_level and log_format from BaseAITBCConfig
    log_format: str = Field(default="json", description="Log format (json or text)")

    # Mempool
    mempool_backend: str = Field(default="database", description="Mempool backend (database, memory)")

    # Blockchain RPC
    blockchain_rpc_url: str = Field(default="http://localhost:8082", description="Blockchain RPC URL")

    # Test Configuration
    test_mode: bool = Field(default=False, description="Test mode")
    test_database_url: str | None = None

    def get_effective_database_url(self) -> str:
        """Get the effective database URL with test mode support."""
        # Use test database if in test mode and test_database_url is set
        if self.test_mode and self.test_database_url:
            return self.test_database_url
        if self.database.url:
            return self.database.url
        # Default SQLite path - consistent with blockchain-node pattern
        return f"sqlite:///{DATA_DIR}/data/coordinator.db"


settings = Settings()

# Enable test mode if environment variable is set
if os.getenv("TEST_MODE") == "true":
    settings.test_mode = True
    if os.getenv("TEST_DATABASE_URL"):
        settings.test_database_url = os.getenv("TEST_DATABASE_URL")

# Note: Secret validation moved to application startup (create_app() or main entry point)
# to allow importing config without production .env files during testing
