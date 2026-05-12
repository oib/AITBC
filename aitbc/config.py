"""
AITBC Configuration Classes
Base configuration classes for AITBC applications
"""

from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

from .constants import DATA_DIR, CONFIG_DIR, LOG_DIR, ENV_FILE
from .aitbc_logging import get_logger

logger = get_logger(__name__)


class BaseAITBCConfig(BaseSettings):
    """
    Base configuration class for all AITBC applications.
    Provides common AITBC-specific settings and environment file loading.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # AITBC system directories
    data_dir: Path = Field(default=DATA_DIR, description="AITBC data directory")
    config_dir: Path = Field(default=CONFIG_DIR, description="AITBC configuration directory")
    log_dir: Path = Field(default=LOG_DIR, description="AITBC log directory")

    # Application settings
    app_name: str = Field(default="AITBC Application", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment (development/staging/production)")
    debug: bool = Field(default=False, description="Debug mode")

    # Logging settings
    log_level: str = Field(default="INFO", description="Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host address")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")

    # Database settings
    database_url: Optional[str] = Field(default=None, description="Database connection URL")
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Maximum overflow connections")
    database_pool_recycle: int = Field(default=3600, description="Connection recycle time in seconds")
    database_pool_pre_ping: bool = Field(default=True, description="Test connections before using")
    database_echo: bool = Field(default=False, description="Enable SQL query logging")

    # Redis settings (if applicable)
    redis_url: Optional[str] = Field(default=None, description="Redis connection URL")
    redis_max_connections: int = Field(default=10, description="Redis max connections")
    redis_timeout: int = Field(default=5, description="Redis timeout in seconds")

    # Security settings
    secret_key: Optional[str] = Field(default=None, description="Application secret key")
    jwt_secret: Optional[str] = Field(default=None, description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiration in hours")

    # Performance settings
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    max_request_size: int = Field(default=10 * 1024 * 1024, description="Max request size in bytes")

    # Rate limiting settings
    rate_limit_requests: int = Field(default=60, description="Rate limit requests per window")
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window in seconds")

    # CORS settings
    allow_origins: List[str] = Field(default_factory=list, description="CORS allowed origins")

    def validate_secrets(self) -> None:
        """Validate that all required secrets are provided."""
        if self.environment == "production":
            if not self.secret_key:
                raise ValueError("SECRET_KEY environment variable is required in production")
            if self.secret_key == "change-me-in-production":
                raise ValueError("SECRET_KEY must be changed from default value")
            if not self.jwt_secret:
                raise ValueError("JWT_SECRET environment variable is required in production")
            if self.jwt_secret == "change-me-in-production":
                raise ValueError("JWT_SECRET must be changed from default value")

    @field_validator("secret_key", "jwt_secret", mode="before")
    @classmethod
    def validate_secret_length(cls, v: Optional[str]) -> Optional[str]:
        """Validate secret key length in production."""
        import os
        if os.getenv("APP_ENV", "development") != "production" and not v:
            return v
        if not v or v.startswith("$") or v == "your_secret_here" or v == "change-me-in-production":
            raise ValueError("Secret must be set to a secure value")
        if len(v) < 32:
            raise ValueError("Secret must be at least 32 characters long")
        return v

    def __init__(self, **kwargs):
        """Initialize AITBC configuration with extended logging"""
        super().__init__(**kwargs)
        logger.info(f"{self.app_name} configured for {self.host}:{self.port}")
        logger.debug(f"Workers: {self.workers}, Request timeout: {self.request_timeout}s")

    def get_redis_cache(self):
        """Get Redis cache instance configured from settings"""
        from .redis_cache import get_cache
        return get_cache(
            redis_url=self.redis_url,
            max_connections=self.redis_max_connections,
            timeout=self.redis_timeout
        )


class AITBCConfig(BaseAITBCConfig):
    """
    Standard AITBC configuration with common settings.
    Inherits from BaseAITBCConfig and can be extended with service-specific fields.
    """

    # Override defaults for standard AITBC application
    app_name: str = Field(default="AITBC Application", description="Application name")
    port: int = Field(default=8000, description="Server port")

    def __init__(self, **kwargs):
        """Initialize AITBC configuration with extended logging"""
        super().__init__(**kwargs)
