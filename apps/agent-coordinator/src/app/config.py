"""
Configuration Management for AITBC Agent Coordinator
"""

import os
from typing import Any

from pydantic import field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseSettings  # type: ignore

    SettingsConfigDict = None  # type: ignore[misc,assignment]
from enum import StrEnum


def validated_cors_origins(origins: list[str]) -> list[str]:
    if "*" in origins:
        raise ValueError("Wildcard CORS origins are not allowed when credentials are enabled")
    return origins


class Environment(StrEnum):
    """Environment types"""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Log levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Application settings"""

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

    # Application settings
    app_name: str = "AITBC Agent Coordinator"
    app_version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # Server settings (standardized: AGENT_COORDINATOR_BIND_HOST/PORT, fallback to HOST/PORT for backward compatibility)
    host: str = os.getenv("AGENT_COORDINATOR_BIND_HOST", os.getenv("HOST", "0.0.0.0"))
    port: int = int(os.getenv("AGENT_COORDINATOR_BIND_PORT", os.getenv("PORT", "9001")))
    workers: int = int(os.getenv("WORKERS", "1"))

    # Redis settings
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
    redis_timeout: int = int(os.getenv("REDIS_TIMEOUT", "5"))

    # Database settings (if needed)
    database_url: str | None = None

    # Agent registry settings
    heartbeat_interval: int = 30  # seconds
    max_heartbeat_age: int = 120  # seconds
    cleanup_interval: int = 60  # seconds
    agent_ttl: int = 86400  # 24 hours in seconds

    # Load balancer settings
    default_strategy: str = "least_connections"
    max_task_queue_size: int = 10000
    task_timeout: int = 300  # 5 minutes

    # Communication settings
    message_ttl: int = 300  # 5 minutes
    max_message_size: int = 1024 * 1024  # 1MB
    connection_timeout: int = 30

    # Security settings
    secret_key: str = os.getenv("SECRET_KEY", "default_secret_key_change_in_production")
    allowed_hosts: list[str] = os.getenv("ALLOWED_HOSTS", "*").split(",") if os.getenv("ALLOWED_HOSTS") else ["*"]
    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "").split(",")
        if os.getenv("CORS_ORIGINS")
        else [
            "http://localhost:8001",
            "http://localhost:8011",
            "http://localhost:8016",
            "http://localhost:9001",
            "http://127.0.0.1:8001",
            "http://127.0.0.1:8011",
            "http://127.0.0.1:8016",
            "http://127.0.0.1:9001",
        ]
    )

    # Monitoring settings
    enable_metrics: bool = True
    metrics_port: int = 9002
    health_check_interval: int = 30

    # Logging settings
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: str | None = None

    # Performance settings
    max_concurrent_tasks: int = 100
    task_batch_size: int = 10
    load_balancer_cache_size: int = 1000

    @field_validator("debug", mode="before")
    @classmethod
    def _parse_bool_env(cls, v: Any) -> bool:
        """Parse boolean-ish env values (true/1/yes vs false/0/no/release)."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off", "release"):
                return False
        return bool(v)

    if SettingsConfigDict is None:

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False


# Global settings instance
settings = Settings()


# Configuration constants
class ConfigConstants:
    """Configuration constants"""

    # Agent types
    AGENT_TYPES = ["coordinator", "worker", "specialist", "monitor", "gateway", "orchestrator"]

    # Agent statuses
    AGENT_STATUSES = ["active", "inactive", "busy", "maintenance", "error"]

    # Message types
    MESSAGE_TYPES = [
        "coordination",
        "task_assignment",
        "status_update",
        "discovery",
        "heartbeat",
        "consensus",
        "broadcast",
        "direct",
        "peer_to_peer",
        "hierarchical",
    ]

    # Task priorities
    TASK_PRIORITIES = ["low", "normal", "high", "critical", "urgent"]

    # Load balancing strategies
    LOAD_BALANCING_STRATEGIES = [
        "round_robin",
        "least_connections",
        "least_response_time",
        "weighted_round_robin",
        "resource_based",
        "capability_based",
        "predictive",
        "consistent_hash",
    ]

    # Default ports
    DEFAULT_PORTS = {
        "agent_coordinator": 9001,
        "agent_registry": 9002,
        "task_distributor": 9003,
        "metrics": 9004,
        "health": 9005,
    }

    # Timeouts (in seconds)
    TIMEOUTS = {"connection": 30, "message": 300, "task": 600, "heartbeat": 120, "cleanup": 3600}

    # Limits
    LIMITS = {
        "max_message_size": 1024 * 1024,  # 1MB
        "max_task_queue_size": 10000,
        "max_concurrent_tasks": 100,
        "max_agent_connections": 1000,
        "max_redis_connections": 10,
    }


# Environment-specific configurations
class EnvironmentConfig:
    """Environment-specific configurations"""

    @staticmethod
    def get_development_config() -> dict[str, Any]:
        """Development environment configuration"""
        return {
            "debug": True,
            "log_level": LogLevel.DEBUG,
            "reload": True,
            "workers": 1,
            "redis_url": "redis://localhost:6379/1",
            "enable_metrics": True,
        }

    @staticmethod
    def get_testing_config() -> dict[str, Any]:
        """Testing environment configuration"""
        return {
            "debug": True,
            "log_level": LogLevel.DEBUG,
            "redis_url": "redis://localhost:6379/15",  # Separate DB for testing
            "enable_metrics": False,
            "heartbeat_interval": 5,  # Faster for testing
            "cleanup_interval": 10,
        }

    @staticmethod
    def get_staging_config() -> dict[str, Any]:
        """Staging environment configuration"""
        return {
            "debug": False,
            "log_level": LogLevel.INFO,
            "redis_url": "redis://localhost:6379/2",
            "enable_metrics": True,
            "workers": 2,
            "cors_origins": ["https://staging.aitbc.com"],
        }

    @staticmethod
    def get_production_config() -> dict[str, Any]:
        """Production environment configuration"""
        return {
            "debug": False,
            "log_level": LogLevel.WARNING,
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            "enable_metrics": True,
            "workers": 4,
            "cors_origins": ["https://aitbc.com"],
            "secret_key": os.getenv("SECRET_KEY"),
            "allowed_hosts": ["aitbc.com", "www.aitbc.com"],
        }


# Configuration loader
class ConfigLoader:
    """Configuration loader and validator"""

    @staticmethod
    def load_config() -> Settings:
        """Load and validate configuration"""
        # Get environment-specific config
        env_config = {}
        if settings.environment == Environment.DEVELOPMENT:
            env_config = EnvironmentConfig.get_development_config()
        elif settings.environment == Environment.TESTING:
            env_config = EnvironmentConfig.get_testing_config()
        elif settings.environment == Environment.STAGING:
            env_config = EnvironmentConfig.get_staging_config()
        elif settings.environment == Environment.PRODUCTION:
            env_config = EnvironmentConfig.get_production_config()

        # Update settings with environment-specific config
        for key, value in env_config.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        # Validate configuration
        ConfigLoader.validate_config()

        return settings

    @staticmethod
    def validate_config() -> None:
        """Validate configuration settings"""
        errors = []

        # Validate required settings
        if not settings.secret_key:
            if settings.environment == Environment.PRODUCTION:
                errors.append("SECRET_KEY must be set in production")

        # Validate ports
        if settings.port < 1 or settings.port > 65535:
            errors.append("Port must be between 1 and 65535")

        # Validate Redis URL
        if not settings.redis_url:
            errors.append("Redis URL is required")

        # Validate timeouts
        if settings.heartbeat_interval <= 0:
            errors.append("Heartbeat interval must be positive")

        if settings.max_heartbeat_age <= settings.heartbeat_interval:
            errors.append("Max heartbeat age must be greater than heartbeat interval")

        # Validate limits
        if settings.max_message_size <= 0:
            errors.append("Max message size must be positive")

        if settings.max_task_queue_size <= 0:
            errors.append("Max task queue size must be positive")

        # Validate strategy
        if settings.default_strategy not in ConfigConstants.LOAD_BALANCING_STRATEGIES:
            errors.append(f"Invalid load balancing strategy: {settings.default_strategy}")

        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")

    @staticmethod
    def get_redis_config() -> dict[str, Any]:
        """Get Redis configuration"""
        return {
            "url": settings.redis_url,
            "max_connections": settings.redis_max_connections,
            "timeout": settings.redis_timeout,
            "decode_responses": True,
            "socket_keepalive": True,
            "socket_keepalive_options": {},
            "health_check_interval": 30,
        }

    @staticmethod
    def get_logging_config() -> dict[str, Any]:
        """Get logging configuration"""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": settings.log_format, "datefmt": "%Y-%m-%d %H:%M:%S"},
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level.value,
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                "": {"level": settings.log_level.value, "handlers": ["console"]},
                "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
                "fastapi": {"level": "INFO", "handlers": ["console"], "propagate": False},
            },
        }


# Configuration utilities
class ConfigUtils:
    """Configuration utilities"""

    @staticmethod
    def get_agent_config(agent_type: str) -> dict[str, Any]:
        """Get configuration for specific agent type"""
        base_config = {
            "heartbeat_interval": settings.heartbeat_interval,
            "max_connections": 100,
            "timeout": settings.connection_timeout,
        }

        # Agent-specific configurations
        agent_configs = {
            "coordinator": {**base_config, "max_connections": 1000, "heartbeat_interval": 15, "enable_coordination": True},
            "worker": {**base_config, "max_connections": 50, "task_timeout": 300, "enable_coordination": False},
            "specialist": {**base_config, "max_connections": 25, "specialization_timeout": 600, "enable_coordination": True},
            "monitor": {**base_config, "heartbeat_interval": 10, "enable_coordination": True, "monitoring_interval": 30},
            "gateway": {**base_config, "max_connections": 2000, "enable_coordination": True, "gateway_timeout": 60},
            "orchestrator": {
                **base_config,
                "max_connections": 500,
                "heartbeat_interval": 5,
                "enable_coordination": True,
                "orchestration_timeout": 120,
            },
        }

        return agent_configs.get(agent_type, base_config)

    @staticmethod
    def get_service_config(service_name: str) -> dict[str, Any]:
        """Get configuration for specific service"""
        base_config = {
            "host": settings.host,
            "port": settings.port,
            "workers": settings.workers,
            "timeout": settings.connection_timeout,
        }

        # Service-specific configurations
        service_configs = {
            "agent_coordinator": {
                **base_config,
                "port": ConfigConstants.DEFAULT_PORTS["agent_coordinator"],
                "enable_metrics": settings.enable_metrics,
            },
            "agent_registry": {
                **base_config,
                "port": ConfigConstants.DEFAULT_PORTS["agent_registry"],
                "enable_metrics": False,
            },
            "task_distributor": {
                **base_config,
                "port": ConfigConstants.DEFAULT_PORTS["task_distributor"],
                "max_queue_size": settings.max_task_queue_size,
            },
            "metrics": {**base_config, "port": ConfigConstants.DEFAULT_PORTS["metrics"], "enable_metrics": True},
            "health": {**base_config, "port": ConfigConstants.DEFAULT_PORTS["health"], "enable_metrics": False},
        }

        return service_configs.get(service_name, base_config)


# Load configuration
config = ConfigLoader.load_config()

# Export settings and utilities
__all__ = ["settings", "config", "ConfigConstants", "EnvironmentConfig", "ConfigLoader", "ConfigUtils"]
