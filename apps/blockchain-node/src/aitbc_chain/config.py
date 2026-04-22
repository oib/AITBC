from __future__ import annotations

from pathlib import Path
from typing import Optional
import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


from pydantic import BaseModel

class ProposerConfig(BaseModel):
    chain_id: str
    proposer_id: str
    interval_seconds: int
    max_block_size_bytes: int
    max_txs_per_block: int

# Default island ID for new installations
DEFAULT_ISLAND_ID = str(uuid.uuid4())

class ChainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="/etc/aitbc/.env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    chain_id: str = ""
    supported_chains: str = "ait-mainnet" # Comma-separated list of supported chain IDs
    db_path: Path = Path("/var/lib/aitbc/data/chain.db")

    rpc_bind_host: str = "0.0.0.0"  # nosec B104: intentional for distributed blockchain
    rpc_bind_port: int = 8080

    p2p_bind_host: str = "0.0.0.0"  # nosec B104: intentional for P2P peer connections
    p2p_bind_port: int = 8001
    p2p_node_id: str = ""

    proposer_id: str = ""
    proposer_key: Optional[str] = None

    mint_per_unit: int = 0  # No new minting after genesis for production
    coordinator_ratio: float = 0.05

    block_time_seconds: int = 10

    # Block production toggle (set false on followers)
    enable_block_production: bool = True

    # Block production limits
    max_block_size_bytes: int = 1_000_000  # 1 MB
    max_txs_per_block: int = 500

    # Only propose blocks if mempool is not empty (prevents empty blocks)
    propose_only_if_mempool_not_empty: bool = False

    # Monitoring interval (in seconds)
    blockchain_monitoring_interval_seconds: int = 60
    min_fee: int = 0  # Minimum fee to accept into mempool

    # Mempool settings
    mempool_backend: str = "database"  # "database" or "memory" (database recommended for persistence)
    mempool_max_size: int = 10_000
    mempool_eviction_interval: int = 60  # seconds

    # Circuit breaker
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: int = 30  # seconds before half-open

    # Sync settings
    trusted_proposers: str = ""  # comma-separated list of trusted proposer IDs
    max_reorg_depth: int = 10  # max blocks to reorg on conflict
    sync_validate_signatures: bool = True  # validate proposer signatures on import
    
    # Automatic bulk sync settings
    auto_sync_enabled: bool = True  # enable automatic bulk sync when gap detected
    auto_sync_threshold: int = 10  # blocks gap threshold to trigger bulk sync
    auto_sync_max_retries: int = 3  # max retry attempts for automatic bulk sync
    min_bulk_sync_interval: int = 60  # minimum seconds between bulk sync attempts
    min_bulk_sync_batch_size: int = 20  # minimum batch size for dynamic bulk sync
    max_bulk_sync_batch_size: int = 200  # maximum batch size for dynamic bulk sync

    gossip_backend: str = "memory"
    gossip_broadcast_url: Optional[str] = None
    default_peer_rpc_url: Optional[str] = None  # HTTP RPC URL of default peer for bulk sync

    # NAT Traversal (STUN/TURN)
    stun_servers: str = ""  # Comma-separated STUN server addresses (e.g., "stun.l.google.com:19302,jitsi.example.com:3478")
    turn_server: Optional[str] = None  # TURN server address (future support)
    turn_username: Optional[str] = None  # TURN username (future support)
    turn_password: Optional[str] = None  # TURN password (future support)

    # Island Configuration (Federated Mesh)
    island_id: str = DEFAULT_ISLAND_ID  # UUID-based island identifier
    island_name: str = "default"  # Human-readable island name
    is_hub: bool = False  # This node acts as a hub
    island_chain_id: str = ""  # Separate chain_id per island (empty = use default chain_id)
    hub_discovery_url: str = "hub.aitbc.bubuit.net"  # Hub discovery DNS
    bridge_islands: str = ""  # Comma-separated list of islands to bridge (optional)

    # Redis Configuration (Hub persistence)
    redis_url: str = "redis://localhost:6379"  # Redis connection URL

    # Keystore for proposer private key (future block signing)
    keystore_path: Path = Path("/var/lib/aitbc/keystore")
    keystore_password_file: Path = Path("/var/lib/aitbc/keystore/.password")


settings = ChainSettings()
