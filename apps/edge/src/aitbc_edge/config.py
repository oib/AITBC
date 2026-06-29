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

    # v0.6.6: Marketplace integration — edge advertises capabilities to marketplace
    marketplace_url: str = "http://localhost:8102"

    # v0.6.6: Agent coordinator integration — edge reports health to agent-coordinator
    agent_coordinator_url: str = "http://localhost:8010"
    agent_heartbeat_interval_seconds: int = 60

    # v0.6.6: Payment verification (feature-flagged — disabled by default)
    require_payment_verification: bool = False

    # JWT auth deferred to v0.7.1 (Bridge Security)
    # cors_origins retained for cross-origin requests
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]


settings = Settings()
