"""
Unified configuration for AITBC Coordinator API

Provides environment-based adapter selection and consolidated settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path
import os


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
        # Auto-generate SQLite URL based on environment
        if self.adapter == "sqlite":
            project_root = self._find_project_root()
            db_path = project_root / "data" / "coordinator.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path}"
        elif self.adapter == "postgresql":
            return "postgresql://localhost:5432/aitbc_coordinator"
        return "sqlite:///:memory:"
    
    @staticmethod
    def _find_project_root() -> Path:
        """Find project root by looking for .git directory."""
        current = Path(__file__).resolve()
        while current.parent != current:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path(__file__).resolve().parents[3]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


class Settings(BaseSettings):
    """Unified application settings with environment-based configuration."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    # Environment
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8011
    
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
        "http://localhost:8011"
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
    
    def validate_secrets(self) -> None:
        """Validate that all required secrets are provided."""
        if self.app_env == "production":
            if not self.jwt_secret:
                raise ValueError("JWT_SECRET environment variable is required in production")
            if self.jwt_secret == "change-me-in-production":
                raise ValueError("JWT_SECRET must be changed from default value")
    
    @property
    def database_url(self) -> str:
        """Get the database URL (backward compatibility)."""
        return self.database.effective_url


settings = Settings()

# Validate secrets on import
settings.validate_secrets()
