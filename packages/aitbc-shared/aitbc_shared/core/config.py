"""Shared configuration base for all AITBC services."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.constants import DATA_DIR, LOG_DIR


class DatabaseConfig(BaseSettings):
    """Database configuration with adapter selection.

    Subclasses can override ``db_filename`` to set a per-service default
    database file (SQLite) or database name (PostgreSQL) without
    reimplementing ``effective_url``.
    """

    adapter: str = "sqlite"  # sqlite, postgresql
    url: str | None = None
    db_filename: str = "service.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True

    @property
    def effective_url(self) -> str:
        """Get the effective database URL."""
        if self.url:
            return self.url

        if self.adapter == "sqlite":
            return f"sqlite:///{DATA_DIR}/data/{self.db_filename}"

        return f"{self.adapter}://localhost:5432/{self.db_filename.removesuffix('.db')}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")


class ServiceSettings(BaseSettings):
    """Base settings for all AITBC microservices."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # Environment
    service_name: str = "aitbc-service"
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_dir: str = str(LOG_DIR / "services")

    # Database
    database: DatabaseConfig = DatabaseConfig()

    # API
    api_prefix: str = "/api/v1"

    # Feature flags
    enable_metrics: bool = True
    enable_health_check: bool = True
