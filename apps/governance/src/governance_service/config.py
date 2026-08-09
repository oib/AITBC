"""Governance service configuration (v0.7.3 §B1, v0.10.7 §B5).

Subclasses ``aitbc_shared.core.config.ServiceSettings`` to inherit common
service fields (service_name, app_env, debug, log_level, database, api_prefix,
enable_metrics, enable_health_check) while adding blockchain integration fields
and governance voting parameters.

All fields are env-var overridable with the ``GOVERNANCE_`` prefix.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

from functools import lru_cache

from aitbc_shared.core.config import ServiceSettings

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(ServiceSettings):
    """Configuration for the AITBC Governance Service."""

    model_config = SettingsConfigDict(env_prefix="governance_", env_file=".env", case_sensitive=False, extra="allow")

    # Service bind (kept for backward compat with GOVERNANCE_BIND_HOST/PORT env vars;
    # ServiceSettings also provides app_host/app_port)
    bind_host: str = Field(default="0.0.0.0")  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    bind_port: int = Field(default=8105)

    # Blockchain integration (v0.7.3) — port 8202 is the canonical blockchain RPC port
    blockchain_rpc_url: str = Field(default=BLOCKCHAIN_RPC_URL)
    default_chain_id: str = Field(default="ait-hub")

    # Governance voting parameters (block-based, ~2s block time)
    voting_period_blocks: int = Field(default=7200)  # ~4 hours at 2s block time
    quorum_percent: float = Field(default=30.0)
    approval_percent: float = Field(default=50.0)
    timelock_blocks: int = Field(default=43200)  # ~24 hours at 2s block time
    snapshot_delay_blocks: int = Field(default=100)  # blocks before voting starts

    # v0.7.4: Emergency proposal parameters
    emergency_timelock_blocks: int = Field(default=7200)  # ~4h at 2s block time (vs 24h normal)
    emergency_quorum_percent: float = Field(default=80.0)  # 80% quorum for emergency
    emergency_voting_period_blocks: int = Field(default=3600)  # ~2h voting (vs 4h normal)
    emergency_approval_percent: float = Field(default=66.67)  # 2/3 supermajority

    # On-chain submission feature flag (disabled until blockchain integration is tested)
    enable_onchain_submission: bool = Field(default=False)

    # V23-18: the execution timelock is a safety control, so it fails closed. A proposal
    # is refused execution unless the service can prove the timelock elapsed — which needs
    # the proposal's on-chain block height and a reachable chain to compare against.
    #
    # Setting this False disables that proof and lets proposals execute immediately. It
    # exists for local development, where there is no chain to record a height on; every
    # bypass is logged at WARNING with the proposal id. Do not set it False in an
    # environment where governance decisions have effect.
    require_execution_timelock: bool = Field(default=True)

    # Proposer signing key for on-chain tx submission (hex-encoded secp256k1 private key)
    # When empty, on-chain submission is skipped (local-only mode).
    proposer_private_key: str = Field(default="")

    # v0.10.1: Target service URLs for parameter automation (applying governance-approved
    # parameter changes to the target service's parameter API after execution).
    poolhub_url: str = Field(default="http://localhost:8103")
    marketplace_url: str = Field(default="http://localhost:8102")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
