from __future__ import annotations

import os
import uuid
from pathlib import Path

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Use the actual data directory where the blockchain database is located
DATA_DIR = Path("/var/lib/aitbc")
KEYSTORE_DIR = DATA_DIR / "keystore"


class ProposerConfig(BaseModel):
    chain_id: str
    proposer_id: str
    interval_seconds: int
    max_block_size_bytes: int
    max_txs_per_block: int
    default_peer_rpc_url: str | None = None


# Default island ID for new installations
DEFAULT_ISLAND_ID = str(uuid.uuid4())


class ChainSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/etc/aitbc/blockchain.env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Node profiles (set during setup.sh)
    blockchain_mode: str = "follower"  # follower or hub
    market_role: str = "customer"  # customer or shop
    hardware_profile: str = "nogpu"  # gpu or nogpu

    chain_id: str = ""
    supported_chains: str = ""  # Comma-separated list of supported chain IDs (defaults to chain_id if empty)
    db_path: Path = DATA_DIR / "data" / "chain.db"
    enforce_state_root_validation: bool = False  # Phase 1.3 enforcement flag
    db_encryption_enabled: bool = False  # Phase 2: SQLCipher database encryption flag (ait-mainnet only)
    db_encryption_key_path: Path = Path("/etc/aitbc/secrets/db_encryption.key")  # Phase 2: Encryption key file path

    # Connection pooling (v0.6.0). Pool size for PostgreSQL/QueuePool-backed
    # engines. SQLite uses StaticPool (single writer) so this only applies when
    # a DATABASE_URL pointing at PostgreSQL is configured. Env var:
    # DB_CONNECTION_POOL_SIZE (default 20).
    db_connection_pool_size: int = 20

    # Auto-resync configuration for Phase 1.3
    auto_resync_enabled: bool = True  # Enable automatic re-sync on rejection threshold
    auto_resync_after_rejections: int = 3  # Trigger re-sync after N consecutive rejections
    auto_resync_source_url: str | None = None  # Trusted peer URL for auto re-sync (fallback to default_peer_rpc_url)

    def get_db_path(self, chain_id: str = "") -> Path:
        """Get database path for a specific chain.

        Args:
            chain_id: Chain ID to get path for. If empty, uses self.chain_id or default.

        Returns:
            Path to chain-specific database file.
        """
        # Resolve chain_id: parameter > settings > environment > empty
        resolved_chain_id = chain_id or self.chain_id or os.getenv("CHAIN_ID", "")

        # First try the standard path: DATA_DIR/data/{chain_id}/chain.db
        standard_path = DATA_DIR / "data" / resolved_chain_id / "chain.db"
        if standard_path.exists():
            return standard_path

        # Fallback to legacy path: /var/lib/aitbc/data/{chain_id}/chain.db
        legacy_path = Path("/var/lib/aitbc/data") / resolved_chain_id / "chain.db"
        if legacy_path.exists():
            return legacy_path

        # If neither exists, return the standard path for creation
        return standard_path

    # CORS configuration
    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if os.getenv("CORS_ORIGINS")
        else ["http://localhost:3000"]
    )

    rpc_bind_host: str = "0.0.0.0"  # nosec B104: intentional for distributed blockchain
    rpc_bind_port: int = 8202

    p2p_bind_host: str = "0.0.0.0"  # nosec B104: intentional for P2P peer connections
    p2p_bind_port: int = 8200
    p2p_node_id: str = ""

    proposer_id: str = ""
    proposer_key: str | None = None

    mint_per_unit: int = 0  # No new minting after genesis for production
    coordinator_ratio: float = 0.05

    block_time_seconds: int = 10

    # Block production toggle (set false on followers)
    enable_block_production: bool = True
    block_production_chains: str = ""  # Comma-separated list of chains to produce blocks for (empty = all supported chains)

    # Block production limits
    max_block_size_bytes: int = 1_000_000  # 1 MB
    max_txs_per_block: int = 500

    # Only propose blocks if mempool is not empty (prevents empty blocks)
    propose_only_if_mempool_not_empty: bool = False  # Deprecated: use block_generation_mode

    # Hybrid block generation settings
    block_generation_mode: str = "hybrid"  # "always", "mempool-only", "hybrid"
    max_empty_block_interval: int = 60  # seconds before forcing empty block (heartbeat)

    # Monitoring interval (in seconds)
    blockchain_monitoring_interval_seconds: int = 60
    min_fee: int = 0  # Minimum fee to accept into mempool

    # Mempool settings
    mempool_backend: str = "database"  # "database" or "memory" (database recommended for persistence)
    mempool_db_url: str = ""  # PostgreSQL URL for mempool (set via MEMPOOL_DB_URL env var - no hardcoded credentials)
    mempool_max_size: int = 10_000
    mempool_eviction_interval: int = 60  # seconds

    # Circuit breaker
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: int = 30  # seconds before half-open

    # Sync settings
    trusted_proposers: str = ""  # comma-separated list of trusted proposer IDs

    @classmethod
    def get_genesis_candidates(cls, chain_id: str) -> list[str]:
        """Get genesis file candidates for a specific chain ID"""
        return [
            str(DATA_DIR / "data" / "genesis.json"),
            f"{DATA_DIR}/data/{chain_id}/genesis.json",
            f"{DATA_DIR}/data/{os.getenv('CHAIN_ID', '')}/genesis.json",
        ]

    @field_validator("chain_configs", mode="before")
    @classmethod
    def parse_chain_configs(cls, v: dict[str, str] | str) -> dict[str, str]:
        """Validate chain_configs dict. Values are raw config strings
        parsed later by ChainConfigParser at point of use."""
        if not v:
            return {}
        if isinstance(v, str):
            import json

            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                raise ValueError(f"chain_configs must be a dict or JSON string, got: {v}") from None
        # Validate each value is a non-empty string
        from aitbc.utils.chain_config import ChainConfigParser

        for chain_id, config_str in v.items():
            if not isinstance(config_str, str):
                raise ValueError(f"chain_configs['{chain_id}'] must be a string, got: {type(config_str)}")
            if config_str.strip():
                ChainConfigParser.parse(config_str)
        return v

    max_reorg_depth: int = 10  # max blocks to reorg on conflict
    sync_validate_signatures: bool = True  # validate proposer signatures on import

    # Automatic bulk sync settings
    auto_sync_enabled: bool = True  # enable automatic bulk sync when gap detected
    auto_sync_threshold: int = 10  # blocks gap threshold to trigger bulk sync
    auto_sync_max_retries: int = 3  # max retry attempts for automatic bulk sync
    min_bulk_sync_interval: int = 60  # minimum seconds between bulk sync attempts
    min_bulk_sync_batch_size: int = 20  # minimum batch size for dynamic bulk sync
    max_bulk_sync_batch_size: int = 200  # maximum batch size for dynamic bulk sync

    # Periodic pull sync settings (for followers)
    periodic_sync_enabled: bool = True  # enable periodic pull sync from default peer
    periodic_sync_interval: int = 30  # seconds between periodic sync attempts

    # Lease-based subscription settings (for followers)
    subscription_enabled: bool = True  # enable lease-based block subscription from hub
    subscription_transport: str = "websocket"  # transport: websocket, http, redis
    lease_duration: int = 3600  # lease duration in seconds (1 hour)
    lease_renewal_threshold: int = 300  # renew lease N seconds before expiry
    heartbeat_interval: int = 60  # heartbeat interval in seconds to extend lease

    # Adaptive sync settings
    initial_sync_threshold: int = 10000  # blocks gap threshold for initial sync mode
    initial_sync_max_batch_size: int = 1000  # max batch size during initial sync
    initial_sync_poll_interval: float = 2.0  # poll interval during initial sync (seconds)
    initial_sync_bulk_interval: int = 10  # min seconds between bulk sync during initial sync
    large_gap_threshold: int = 1000  # blocks gap threshold for large gap mode
    large_gap_max_batch_size: int = 500  # max batch size during large gap sync
    large_gap_poll_interval: float = 3.0  # poll interval during large gap sync (seconds)
    large_gap_bulk_interval: int = 30  # min seconds between bulk sync during large gap

    gossip_backend: str = "memory"
    gossip_broadcast_url: str | None = os.getenv("GOSSIP_BROADCAST_URL", "redis://127.0.0.1:6379")
    default_peer_rpc_url: str | None = None  # HTTP RPC URL of default peer for bulk sync

    # Cross-site synchronization settings
    cross_site_sync_enabled: bool = True
    cross_site_remote_endpoints: list[str] = (
        os.getenv("CROSS_SITE_REMOTE_ENDPOINTS", "").split(",") if os.getenv("CROSS_SITE_REMOTE_ENDPOINTS") else []
    )
    cross_site_poll_interval: int = 10

    # NAT Traversal (STUN/TURN)
    stun_servers: str = ""  # Comma-separated STUN server addresses (e.g., "stun.l.google.com:19302,jitsi.example.com:3478")
    turn_server: str | None = None  # TURN server address (future support)
    turn_username: str | None = None  # TURN username (future support)
    turn_password: str | None = None  # TURN password (future support)

    # Island Configuration (Federated Mesh)
    island_id: str = DEFAULT_ISLAND_ID  # UUID-based island identifier
    island_name: str = "default"  # Human-readable island name
    is_hub: bool = False  # This node acts as a hub
    island_chain_id: str = ""  # Separate chain_id per island (empty = use default chain_id)
    hub_discovery_url: str = "hub.aitbc.bubuit.net"  # Hub discovery DNS
    bridge_islands: str = ""  # Comma-separated list of islands to bridge (optional)

    # Multi-island sync sources (v0.6.3). Per-chain hub URL mapping.
    # Format: "chain_id:url,chain_id:url,..."
    # Chains not in this mapping fall back to default_peer_rpc_url.
    # Env var: CHAIN_SYNC_SOURCES
    chain_sync_sources: str = ""

    # Island registry (v0.6.3). Maps island_id to chain_id and hub_url.
    # Format: "island_id:chain_id:hub_url,island_id:chain_id:hub_url,..."
    # Optional 4th field: island_name (defaults to island_id).
    # Env var: ISLAND_REGISTRY
    island_registry: str = ""

    # Per-chain gossip backends (v0.6.3). Optional.
    # Format: "chain_id:redis://url,chain_id:redis://url,..."
    # If empty, all chains use the shared gossip_backend/gossip_broadcast_url.
    # Env var: GOSSIP_BACKENDS
    gossip_backends: str = ""

    # Island manager background tasks (v0.6.3). When enabled, the island
    # manager starts bridge request monitoring and island health checks.
    # Default off for safety — enable with ISLAND_TASKS_ENABLED=true.
    island_tasks_enabled: bool = False

    # Island health check interval in seconds (v0.6.3).
    island_health_check_interval: int = 30

    # Bridge request monitor interval in seconds (v0.6.3).
    bridge_request_monitor_interval: int = 60

    # Multi-chain per island (v0.6.4). Chains hosted on this island.
    # Comma-separated list of chain_ids. If empty, defaults to [chain_id]
    # for backward compat with single-chain config.
    # Env var: ISLAND_CHAINS
    island_chains: str = ""

    # Per-chain configuration overrides (v0.6.4).
    # Parsed via ChainConfigParser (aitbc.utils.chain_config).
    # Env vars: CHAIN_CONFIG_<chain_id>="block_time_seconds:2,max_txs_per_block:500"
    # Stored as dict[str, str] by pydantic, parsed by field_validator.
    chain_configs: dict[str, str] = {}

    # Per-chain port offsets (v0.6.4). Offset from base RPC/P2P ports.
    # Format: "chain_id:offset,chain_id:offset,..."
    # Env var: CHAIN_PORT_OFFSETS
    chain_port_offsets: str = ""

    # Multi-chain startup retry config (v0.6.4).
    # Main chain fails fast; secondary chains retry with exponential backoff.
    multi_chain_start_max_retries: int = 3
    multi_chain_start_base_delay: float = 2.0
    multi_chain_start_max_delay: float = 30.0
    multi_chain_start_backoff_multiplier: float = 2.0

    # Multi-chain health monitoring (v0.6.4).
    multi_chain_health_interval: int = 60

    # Chain shutdown timeout (v0.6.4). Graceful stop wait in seconds.
    chain_shutdown_timeout: int = 10

    # Cross-chain bridge release fence (v0.5.16 → v0.7.2 UNFENCED).
    # The bridge release path (confirm_transfer / /bridge/confirm) now uses
    # full cryptographic verification: Merkle proof verification against
    # stored block headers (v0.7.2 §B3), block header signature verification
    # against the v0.7.1 validator set (v0.7.2 §B4), finality tracking
    # (v0.7.2 §B5), and multi-sig threshold signatures (v0.7.1 §B6).
    # The fence is now UNFENCED (default true) — set BRIDGE_RELEASE_ENABLED=false
    # to re-fence on isolated test/dev networks.
    bridge_release_enabled: bool = True

    # Bridge configuration (v0.7.0). Operational parameters for the cross-chain
    # bridge. Defaults mirror the constants in aitbc/constants.py
    # (BRIDGE_TIMEOUT_SECONDS, BRIDGE_RETRY_LIMIT, etc.) so they can be tuned
    # per-deployment via env vars without code changes.
    bridge_timeout: int = 300  # Seconds before a transfer is considered stale
    bridge_retry_limit: int = 3  # Retry attempts for failed bridge operations
    bridge_fee_basis_points: int = 10  # Bridge fee in basis points (10 = 0.1%)
    bridge_supported_chains: str = ""  # Comma-separated list of chain IDs the bridge serves
    bridge_batch_size: int = 10  # Max transfers per batch operation
    bridge_monitor_interval: int = 60  # Seconds between bridge health checks
    bridge_stuck_transfer_timeout: int = 3600  # Seconds before a pending transfer is flagged as stuck

    # Bridge multi-sig configuration (v0.7.1). Security layer for the
    # cross-chain bridge: M-of-N validators must sign each proof before
    # funds can be released. Defaults match aitbc/constants.py. The release
    # fence (bridge_release_enabled) stays in place until v0.7.2 completes
    # Merkle proof verification — multi-sig is an additional layer, not a
    # replacement for the fence.
    bridge_multisig_enabled: bool = False  # require multi-sig for confirm
    bridge_multisig_threshold: int = 3  # M-of-N minimum signatures
    bridge_multisig_validators: int = 5  # N total validators
    bridge_multisig_timeout: int = 3600  # seconds to collect signatures
    bridge_validator_set_grace_period: int = 7200  # seconds — old epoch valid during rotation
    bridge_block_signature_required: bool = True  # require block header signatures

    # Bridge verification configuration (v0.7.2). Replaces the trivially
    # forgeable field-equality proof validation with cryptographic Merkle
    # proof verification against stored block headers. The release fence
    # (bridge_release_enabled) is unfenced after this verification is
    # operational and tested.
    bridge_verification_mode: str = "in_process"  # "in_process" | "oracle"
    bridge_min_confirmations: int = 3  # minimum confirmations for any transfer
    bridge_finality_blocks: int = 6  # full finality threshold
    bridge_large_transfer_threshold: int = 10000  # transfers above this require full finality

    # External oracle configuration (v0.7.4). When bridge_verification_mode
    # is "oracle", bridge proof verification calls an external oracle service
    # instead of the in-process verifier. The in-process verifier remains as
    # a fallback when oracle endpoints are unreachable.
    bridge_oracle_endpoints: list[str] = []  # External oracle endpoints (e.g. ["http://oracle-1:9000"])
    bridge_oracle_health_check_interval: int = 60  # seconds between oracle health checks
    bridge_oracle_timeout: int = 30  # seconds before an oracle request times out

    # Network compression (v0.6.0). When enabled, gossip/Redis/P2P payloads are
    # gzip-compressed before transmission and decompressed on receive. Env var:
    # NETWORK_COMPRESSION_ENABLED (default true).
    network_compression_enabled: bool = True

    # Parallel processing (v0.6.1). Feature flag for parallel transaction
    # validation via dependency analysis. Default off for safety — enable with
    # PARALLEL_TX_VALIDATION=true. PARALLEL_WORKERS sets the thread pool size
    # for parallel tx validation (default 4). CONFLICT_THRESHOLD is the fraction
    # of conflicting transactions above which the proposer falls back to
    # sequential validation (default 0.5 = 50%).
    parallel_tx_validation: bool = False  # Feature flag — default off for safety
    parallel_workers: int = 4  # Thread pool size for parallel tx validation
    conflict_threshold: float = 0.5  # Fall back to sequential if >50% of txs conflict

    # Gossip protocol (v0.6.2). Protocol version advertises the message
    # format capabilities of this node. v1 = legacy (pre-v0.6.2, no
    # priority/batching). v2 = optimized (priority queue + batching).
    # GOSSIP_BACKWARD_COMPAT=true keeps accepting v1 peers (with a
    # deprecation log) for one release cycle. GOSSIP_LEGACY_PEER_TIMEOUT
    # is the seconds before disconnecting a v1 peer that never upgrades.
    # GOSSIP_MESSAGE_BATCH_SIZE is the max messages per batched gossip
    # frame (1 = no batching). GOSSIP_PRIORITY_ENABLED toggles the
    # PriorityMessageQueue routing in the broker (default off).
    gossip_protocol_version: int = 2  # Protocol version (1=legacy, 2=optimized)
    gossip_backward_compat: bool = True  # Accept v1 peers with deprecation
    gossip_legacy_peer_timeout: int = 3600  # Seconds before disconnecting v1 peers
    gossip_message_batch_size: int = 10  # Max messages per batched gossip frame
    gossip_priority_enabled: bool = False  # Enable message prioritization (default off)

    # Parallel sync (v0.6.2). Feature flag for parallel block fetching
    # from multiple peers. Default off for safety — enable with
    # SYNC_PARALLEL_ENABLED=true. SYNC_PARALLEL_MAX_PEERS caps the number
    # of peers used concurrently for block range requests.
    # SYNC_PARALLEL_TIMEOUT is the per-peer request timeout in seconds.
    sync_parallel_enabled: bool = False  # Feature flag — default off for safety
    sync_parallel_max_peers: int = 4  # Max peers for parallel block fetching
    sync_parallel_timeout: float = 30.0  # Timeout per peer request (seconds)

    # Delta sync (v0.6.2). Feature flag for delta-based state sync —
    # only the accounts that changed between two heights are
    # transferred, instead of the full state snapshot. Default off for
    # safety — enable with SYNC_DELTA_ENABLED=true.
    # SYNC_DELTA_THRESHOLD is the fraction of full-state size above
    # which delta sync falls back to full sync (default 0.5 = 50%).
    # SYNC_DELTA_MAX_BLOCKS caps the gap size eligible for delta sync
    # (above this, full sync is used to bound diff computation cost).
    sync_delta_enabled: bool = False  # Feature flag — default off for safety
    sync_delta_threshold: float = 0.5  # Fall back to full sync if delta > 50% of state
    sync_delta_max_blocks: int = 100  # Max blocks for delta sync (use full sync above this)

    # P2P-to-RPC port offset (v0.6.2). The RPC HTTP port is derived from the
    # P2P listen port by adding this offset (P2P 8200 -> RPC 8202). Used by
    # the peer capability exchange to construct a peer's RPC URL from the
    # address/port advertised in the P2P handshake. Env var:
    # P2P_TO_RPC_PORT_OFFSET (default 2).
    p2p_to_rpc_port_offset: int = 2  # RPC port = P2P port + offset (8200 -> 8202)

    # Redis Configuration (Hub persistence)
    redis_url: str = "redis://localhost:6379"  # Redis connection URL

    # Keystore for proposer private key (future block signing)
    keystore_path: Path = KEYSTORE_DIR
    keystore_password_file: Path = KEYSTORE_DIR / ".password"


settings = ChainSettings()
