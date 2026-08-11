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
    app_host: str = "0.0.0.0"  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    app_port: int = 8111
    api_prefix: str = "/v1"

    # Database — uses shared adapter logic with edge-specific filename.
    #
    # V23-47: the environment variables are ADAPTER and URL, not DATABASE_ADAPTER and
    # DATABASE_URL as this comment used to say. DatabaseConfig is a BaseSettings with no
    # env_prefix, so its fields map to the bare names. Setting DATABASE_URL has no effect at
    # all and the service silently keeps its default file, which is how an Alembic run aimed
    # at a scratch copy landed on the deployed database instead. `URL` is a dangerously
    # generic name for this; renaming it means an env_prefix on the shared DatabaseConfig and
    # a coordinated change across every service that uses it, so it is documented here rather
    # than changed unilaterally.
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
    agent_coordinator_url: str = "http://localhost:8107"
    agent_heartbeat_interval_seconds: int = 60

    # v0.6.6: Payment verification (v0.10.1: enabled by default for end-to-end flow)
    require_payment_verification: bool = True

    # JWT auth deferred to v0.7.1 (Bridge Security)
    # cors_origins retained for cross-origin requests
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]


settings = Settings()
