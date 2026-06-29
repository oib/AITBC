"""Governance service configuration (v0.7.3 §B1).

Provides a ``pydantic_settings.BaseSettings`` subclass with blockchain
integration fields (RPC URL, chain_id) and governance voting parameters
(voting period, quorum, approval threshold, timelock, snapshot delay).

All fields are env-var overridable with the ``GOVERNANCE_`` prefix.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the AITBC Governance Service."""

    model_config = SettingsConfigDict(env_prefix="governance_", env_file=".env", case_sensitive=False)

    # Service bind
    bind_host: str = Field(default="0.0.0.0")
    bind_port: int = Field(default=8105)

    # Blockchain integration (v0.7.3) — port 8202 is the canonical blockchain RPC port
    blockchain_rpc_url: str = Field(default="http://localhost:8202")
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

    # Proposer signing key for on-chain tx submission (hex-encoded secp256k1 private key)
    # When empty, on-chain submission is skipped (local-only mode).
    proposer_private_key: str = Field(default="")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
