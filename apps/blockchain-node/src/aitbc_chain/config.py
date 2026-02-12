from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    chain_id: str = "ait-devnet"
    db_path: Path = Path("./data/chain.db")

    rpc_bind_host: str = "127.0.0.1"
    rpc_bind_port: int = 8080

    p2p_bind_host: str = "127.0.0.2"
    p2p_bind_port: int = 7070

    proposer_id: str = "ait-devnet-proposer"
    proposer_key: Optional[str] = None

    mint_per_unit: int = 1000
    coordinator_ratio: float = 0.05

    block_time_seconds: int = 2

    # Block production limits
    max_block_size_bytes: int = 1_000_000  # 1 MB
    max_txs_per_block: int = 500
    min_fee: int = 0  # Minimum fee to accept into mempool

    # Mempool settings
    mempool_backend: str = "memory"  # "memory" or "database"
    mempool_max_size: int = 10_000
    mempool_eviction_interval: int = 60  # seconds

    # Circuit breaker
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: int = 30  # seconds before half-open

    # Sync settings
    trusted_proposers: str = ""  # comma-separated list of trusted proposer IDs
    max_reorg_depth: int = 10  # max blocks to reorg on conflict
    sync_validate_signatures: bool = True  # validate proposer signatures on import

    gossip_backend: str = "memory"
    gossip_broadcast_url: Optional[str] = None


settings = ChainSettings()
