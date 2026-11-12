"""Configuration for AITBC Market Service (v0.6.6, v0.10.7 §B5).

Subclasses ``aitbc_shared.core.config.ServiceSettings`` to inherit common
service fields (service_name, app_env, debug, log_level, database, api_prefix,
enable_metrics, enable_health_check) while adding blockchain and agent
coordinator integration fields.
"""

from __future__ import annotations

import logging
import os

from aitbc.constants import BLOCKCHAIN_RPC_URL

from aitbc_shared.core.config import ServiceSettings

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(ServiceSettings):
    """Market service settings (v0.6.6)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # API key for governance/admin endpoints (e.g. live parameter changes)
    auth_enabled: bool = True
    api_key: str | None = None
    # Operator-tier credential (#1893): distinct from ``api_key`` so user-facing
    # key holders cannot invoke operator actions (dispute resolution, unsigned
    # party routes). Must differ from ``api_key``; when unset the operator tier
    # is closed (fail closed). Reads MARKET_OPERATOR_API_KEY — the name the
    # docs, provisioning and tests use; OPERATOR_API_KEY accepted as a legacy
    # fallback. (``api_key`` deliberately reads plain ``API_KEY``; the
    # MARKET_API_KEY name is the user/CLI-side credential.)
    operator_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MARKET_OPERATOR_API_KEY", "OPERATOR_API_KEY"),
    )

    # Blockchain integration
    blockchain_rpc_url: str = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL)
    blockchain_rpc_api_key: str = os.getenv("BLOCKCHAIN_RPC_API_KEY", "")
    default_chain_id: str = ""

    # Agent coordinator integration (v0.6.6 matching → task queue)
    agent_coordinator_url: str = "http://localhost:8107"

    # Compute hub RPC endpoint published in market offers.
    # Default uses https per V23-13; override via HUB_RPC_URL env var.
    hub_rpc_url: str = "https://hub.aitbc.invalid/rpc"

    # Rate limiting (V23-32a). Applied per client IP by RateLimitMiddleware in main.py.
    # 120/minute is roughly two requests a second sustained, which no legitimate UI or agent
    # workflow against this service approaches, while still bounding a scripted client.
    # AITBC_ENABLE_RATE_LIMITING=false disables it outside production; production cannot.
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Service binding (kept for backward compat with MARKET_BIND_HOST/PORT env vars;
    # ServiceSettings also provides app_host/app_port).
    market_bind_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("MARKET_BIND_HOST"),
        # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    )  # nosec B104
    market_bind_port: int = Field(
        default=8102,
        validation_alias=AliasChoices("MARKET_BIND_PORT"),
    )

    @model_validator(mode="after")
    def _check_operator_key_distinct(self) -> Settings:
        """#1906: an operator key equal to the user key silently collapses the
        tiers — ``_is_operator`` fails closed at runtime, so every operator
        action is refused with no explanation. Warn loudly at startup."""
        if self.operator_api_key is not None and self.api_key is not None and self.operator_api_key == self.api_key:
            logger.warning(
                "MARKET_OPERATOR_API_KEY equals API_KEY — the operator tier is "
                "disabled (all operator actions will 403). Set a distinct "
                "MARKET_OPERATOR_API_KEY."
            )
        return self


settings = Settings()
