"""Configuration for AITBC Marketplace Service (v0.6.6, v0.10.7 §B5).

Subclasses ``aitbc_shared.core.config.ServiceSettings`` to inherit common
service fields (service_name, app_env, debug, log_level, database, api_prefix,
enable_metrics, enable_health_check) while adding blockchain and agent
coordinator integration fields.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

from aitbc_shared.core.config import ServiceSettings

from pydantic_settings import SettingsConfigDict


class Settings(ServiceSettings):
    """Marketplace service settings (v0.6.6)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # API key for governance/admin endpoints (e.g. live parameter changes)
    auth_enabled: bool = True
    api_key: str | None = None

    # Blockchain integration
    blockchain_rpc_url: str = BLOCKCHAIN_RPC_URL
    default_chain_id: str = "ait-hub"

    # Agent coordinator integration (v0.6.6 matching → task queue)
    agent_coordinator_url: str = "http://localhost:8107"

    # Compute hub RPC endpoint published in marketplace offers.
    # ponytail: default uses https per V23-13; override via HUB_RPC_URL env var.
    hub_rpc_url: str = "https://hub.aitbc.bubuit.net/rpc"

    # Rate limiting (V23-32a). Applied per client IP by RateLimitMiddleware in main.py.
    # 120/minute is roughly two requests a second sustained, which no legitimate UI or agent
    # workflow against this service approaches, while still bounding a scripted client.
    # AITBC_ENABLE_RATE_LIMITING=false disables it outside production; production cannot.
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Service binding (kept for backward compat with MARKETPLACE_BIND_HOST/PORT env vars;
    # ServiceSettings also provides app_host/app_port)
    marketplace_bind_host: str = "0.0.0.0"  # nosec B104
    marketplace_bind_port: int = 8102


settings = Settings()
