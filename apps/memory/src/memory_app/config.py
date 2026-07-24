"""Configuration for the memory service."""

from pydantic_settings import SettingsConfigDict

from aitbc_shared import DatabaseConfig, ServiceSettings


class MemoryDatabaseConfig(DatabaseConfig):
    """Database configuration for the memory service."""

    db_filename: str = "memory.db"


class Settings(ServiceSettings):
    """Memory service settings."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    service_name: str = "aitbc-memory"
    app_host: str = "0.0.0.0"
    app_port: int = 8112
    api_prefix: str = "/v1"

    database: MemoryDatabaseConfig = MemoryDatabaseConfig()

    # Encryption-at-rest master key. If unset, data is stored plaintext with a warning.
    memory_master_key: str | None = None


settings = Settings()
