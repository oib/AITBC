"""Shared configuration base for all AITBC services."""

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.constants import DATA_DIR, LOG_DIR


def _database_adapter_from_scheme(scheme: str) -> str:
    scheme = scheme.lower()
    if scheme == "postgres":
        return "postgresql"
    return scheme


class DatabaseConfig(BaseSettings):
    """Database configuration with adapter selection.

    Subclasses can override ``db_filename`` to set a per-service default
    database file (SQLite) or database name (PostgreSQL) without
    reimplementing ``effective_url``.

    By default the service uses SQLite. To use ``DATABASE_URL``, set
    ``DATABASE_ADAPTER`` to a matching scheme (``sqlite`` or ``postgresql``).
    This avoids silently switching a running deployment from SQLite to
    PostgreSQL just because ``DATABASE_URL`` happens to be present in the
    environment.
    """

    adapter: str = "sqlite"  # sqlite, postgresql
    url: str | None = None
    db_filename: str = "service.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True

    @model_validator(mode="before")
    @classmethod
    def _load_legacy_database_url(cls, data):
        """Allow ``DATABASE_URL`` / ``DATABASE_ADAPTER`` to populate the config.

        An explicit ``url`` or ``adapter`` in the settings still wins over the
        environment. ``DATABASE_URL`` is only used when ``DATABASE_ADAPTER`` is
        also provided, so deployments with a stale or inherited ``DATABASE_URL``
        do not accidentally switch to a different database.
        """
        if not isinstance(data, dict):
            return data

        url = data.get("url")
        adapter = data.get("adapter")
        env_url = data.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
        env_adapter = data.get("DATABASE_ADAPTER") or os.environ.get("DATABASE_ADAPTER")

        if url is None and env_url is not None and env_adapter is not None:
            scheme = _database_adapter_from_scheme(env_url.split("://", 1)[0])
            requested = _database_adapter_from_scheme(env_adapter)
            if scheme == requested:
                # SQLAlchemy dialect is ``postgresql``, not ``postgres``.
                if scheme == "postgresql" and not env_url.startswith("postgresql://"):
                    env_url = "postgresql" + env_url[env_url.index("://"):]
                data["url"] = env_url
                data["adapter"] = requested
        return data

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
