"""Configuration for Agent Management Service"""

from pydantic import Field

from aitbc_shared import DatabaseConfig as BaseDatabaseConfig
from aitbc_shared import ServiceSettings as BaseServiceSettings


class DatabaseConfig(BaseDatabaseConfig):
    """Database configuration for agent-management service."""

    db_filename: str = "agent_management.db"


class ServiceSettings(BaseServiceSettings):
    """Settings for agent-management service."""

    # Override defaults for agent-management
    service_name: str = "aitbc-agent-management"
    app_port: int = 8204
    api_prefix: str = "/v1"

    # API Keys (comma-separated in env)
    admin_api_keys: list[str] = Field(default_factory=list)
    client_api_keys: list[str] = Field(default_factory=list)
    miner_api_keys: list[str] = Field(default_factory=list)


# Global settings instance
settings = ServiceSettings()
