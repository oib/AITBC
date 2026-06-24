"""Configuration for Edge API Service"""

from pydantic_settings import SettingsConfigDict

from aitbc_shared import DatabaseConfig, ServiceSettings


class EdgeDatabaseConfig(DatabaseConfig):
    """Database configuration for edge service."""

    db_filename: str = "aitbc_edge.db"


class Settings(ServiceSettings):
    """Edge API settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # Override defaults for edge service
    service_name: str = "aitbc-edge"
    app_host: str = "0.0.0.0"
    app_port: int = 8111
    api_prefix: str = "/v1"

    # Database — uses shared adapter logic with edge-specific filename.
    # Set DATABASE_ADAPTER=postgresql and DATABASE_URL=... in production.
    database: EdgeDatabaseConfig = EdgeDatabaseConfig()

    # Blockchain node RPC settings
    blockchain_rpc_host: str = "localhost"
    blockchain_rpc_port: int = 8202

    # GPU service settings
    gpu_service_host: str = "localhost"
    gpu_service_port: int = 8101

    # JWT settings — must be set via JWT_SECRET_KEY env var in production
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]


settings = Settings()
