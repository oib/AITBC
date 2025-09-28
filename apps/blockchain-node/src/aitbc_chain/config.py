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

    p2p_bind_host: str = "0.0.0.0"
    p2p_bind_port: int = 7070

    proposer_id: str = "ait-devnet-proposer"
    proposer_key: Optional[str] = None

    mint_per_unit: int = 1000
    coordinator_ratio: float = 0.05

    block_time_seconds: int = 2

    gossip_backend: str = "memory"
    gossip_broadcast_url: Optional[str] = None


settings = ChainSettings()
