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

    # Blockchain integration
    blockchain_rpc_url: str = BLOCKCHAIN_RPC_URL
    default_chain_id: str = "ait-hub"

    # Agent coordinator integration (v0.6.6 matching → task queue)
    agent_coordinator_url: str = "http://localhost:8107"

    # Service binding (kept for backward compat with MARKETPLACE_BIND_HOST/PORT env vars;
    # ServiceSettings also provides app_host/app_port)
    marketplace_bind_host: str = "0.0.0.0"  # nosec B104
    marketplace_bind_port: int = 8102


settings = Settings()
