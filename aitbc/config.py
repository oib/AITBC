"""
AITBC Configuration Classes
Base configuration classes for AITBC applications
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from .constants import DATA_DIR, CONFIG_DIR, LOG_DIR, ENV_FILE


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
    
    class Config:
        """Pydantic configuration"""
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        case_sensitive = False


class AITBCConfig(BaseAITBCConfig):
    """
    Standard AITBC configuration with common settings.
    Inherits from BaseAITBCConfig and adds AITBC-specific fields.
    """
    
    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host address")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")
    
    # Database settings
    database_url: Optional[str] = Field(default=None, description="Database connection URL")
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    
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
