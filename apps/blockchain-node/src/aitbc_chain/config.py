from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Re-exported from aitbc.constants rather than spelled out again. This module used to hold its
# own `Path("/var/lib/aitbc")`, which is the same value the shared constant already resolves
# to -- except that the shared one honours `AITBC_DATA_DIR` and this copy did not. That is how
# the test suite came to create `chain-a/` and `chain-sig/`, named after test-only chain IDs,
# inside the deployed data directory: nothing the tests could set moved this path (V23-73).
from aitbc.constants import DATA_DIR

KEYSTORE_DIR = DATA_DIR / "keystore"

# AITBC_CHAIN_ENV_FILE lets tests (and alternate deployments) override the env file
# the chain settings are loaded from. Set it to "" to load no env file.
_chain_env_raw = os.environ.get("AITBC_CHAIN_ENV_FILE")
if _chain_env_raw is None:
    _CHAIN_ENV_FILES: list[str] = ["/etc/aitbc/blockchain.env"]
elif _chain_env_raw:
    _CHAIN_ENV_FILES = [p for p in _chain_env_raw.split(",") if p]
else:
    _CHAIN_ENV_FILES = []


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
        env_file=_CHAIN_ENV_FILES, env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Node profiles (set during setup.sh)
    blockchain_mode: str = "follower"  # follower or hub
    market_role: str = "customer"  # customer or shop
    hardware_profile: str = "nogpu"  # gpu or nogpu

    chain_id: str = ""
    supported_chains: str = ""  # Comma-separated list of supported chain IDs (defaults to chain_id if empty)
    db_path: Path = DATA_DIR / "data" / "chain.db"
    db_encryption_enabled: bool = False  # Phase 2: SQLCipher database encryption flag (ait-mainnet only)
    db_encryption_key_path: Path = Path("/etc/aitbc/secrets/db_encryption.key")  # Phase 2: Encryption key file path
    # Hold one idle SQLite connection per chain for the life of the process. Every session opens its
    # own connection (NullPool), so whenever none is open the closing one is the *last*, and SQLite
    # checkpoints and deletes the WAL under an EXCLUSIVE lock while it syncs the disk. On btrfs over
    # spinning disks (fsync median ~220 ms, outliers over 1.7 s) that lock was held for seconds, and
    # every connection opened meanwhile failed after a 5 s wait with "database is locked". With a
    # keeper nobody is last: the WAL stays on disk and is only checkpointed passively. Off by default.
    # While it is on, copy chain.db with `sqlite3 .backup` or with the node stopped, never with a bare
    # `cp`, and only open a `.backup` copy with immutable=1: a live file's recent commits sit in the WAL.
    db_keeper_connection: bool = False

    # Connection pooling (v0.6.0). Pool size for PostgreSQL/QueuePool-backed
    # engines. SQLite uses StaticPool (single writer) so this only applies when
    # a DATABASE_URL pointing at PostgreSQL is configured. Env var:
    # DB_CONNECTION_POOL_SIZE (default 20).
    db_connection_pool_size: int = 20

    # Auto-resync configuration for Phase 1.3
    auto_resync_enabled: bool = True  # Enable automatic re-sync on rejection threshold
    auto_resync_after_rejections: int = 3  # Trigger re-sync after N consecutive rejections
    auto_resync_source_url: str | None = None  # Trusted peer URL for auto re-sync (fallback to default_peer_rpc_url)

    # Divergence reporting (V23-90). Divergence is not auto-resolved: pulling cannot fix it, since
    # the peer is behind us, and discarding accepted local history is an operator's decision.
    divergence_after_rejections: int = 3  # Report after N consecutive divergent pushed blocks
    divergence_report_interval: int = 300  # Seconds between repeated reports for the same chain

    def get_db_path(self, chain_id: str = "") -> Path:
        """Get database path for a specific chain.

        Args:
            chain_id: Chain ID to get path for. If empty, uses self.chain_id or default.

        Returns:
            Path to chain-specific database file.
        """
        # Resolve chain_id: parameter > settings > environment > empty
        resolved_chain_id = chain_id or self.chain_id or os.getenv("CHAIN_ID", "")

        # The "legacy path" fallback that used to sit here was `Path("/var/lib/aitbc/data") /
        # chain_id / "chain.db"` -- byte for byte what this expression produced, since DATA_DIR
        # was that literal. It could never be reached. Now that DATA_DIR follows
        # AITBC_DATA_DIR, keeping it would have been worse than dead: a run pointed at a
        # temporary directory would have fallen back to the deployed one (V23-73).
        return DATA_DIR / "data" / resolved_chain_id / "chain.db"

    @model_validator(mode="after")
    def _default_supported_chains(self) -> ChainSettings:
        """Default supported_chains to chain_id when empty.

        Without this, when SUPPORTED_CHAINS is unset the island ID is
        constructed as ``"-island"`` (empty string + suffix). Defaulting
        to ``chain_id`` produces a valid island ID like
        ``"ait-localnet-island"``.
        """
        if not self.supported_chains.strip():
            self.supported_chains = self.chain_id
        return self

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

    contact_email: str = os.getenv("CONTACT_EMAIL", "operator@aitbc.invalid")

    proposer_id: str = ""
    proposer_key: str | None = None

    # Genesis key used for governance execution, fee subsidies, and other
    # chain-level operations. Preferably loaded from node.env / secrets.
    genesis_private_key: str | None = None
    genesis_address: str | None = None

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
    mempool_eviction_interval: int = 60  # seconds between staleness sweeps
    # How long an entry may sit unmined before the sweeper drops it. A follower
    # never proposes, so nothing drains its mempool; a transaction submitted
    # there whose peer fan-out failed would otherwise sit forever, and the
    # sqlite backend means it survives restarts. Generous by design -- this is a
    # garbage collector for stranded entries, not a fee-pressure mechanism.
    mempool_entry_ttl: int = 3600  # seconds; 0 disables the sweeper
    # Per-transaction body cap at intake. Anything larger can never fit a block
    # (max_block_size_bytes) and would only squat in the pool until expiry.
    mempool_max_tx_size_bytes: int = 131072  # 128 KiB
    # Seconds between settlement-mark sweeps (demote-only lite reconciler).
    # 0 disables it.
    escrow_settlement_sweep_interval: int = 60
    # Periodic fee-residue pass (Task A4): runs inside the settlement-mark
    # sweeper's tick, so it shares escrow_settlement_sweep_interval. A job is
    # only a candidate when its newest sealed settlement leg is older than
    # the grace period, so a metered multi-leg settle is never interrupted.
    escrow_fee_sweep_pass_grace_seconds: int = 300
    # Ignore any job with a settlement leg below this height. Defaults to the
    # v11 activation: sweeps have no consensus meaning below it, and the
    # pre-v11 custody census is an operator decision the pass must not take.
    escrow_fee_sweep_pass_min_height: int = 35400
    # Bounded work per pass: at most this many settled rows are inspected.
    escrow_fee_sweep_pass_max_jobs: int = 50
    # How many nonces ahead of the account nonce a pending transaction may sit.
    # Admission rejects beyond this so one sender cannot queue an unbounded
    # pipeline of not-yet-executable transactions.
    mempool_nonce_lookahead: int = 16

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
                parsed = json.loads(v)
            except json.JSONDecodeError:
                raise ValueError(f"chain_configs must be a dict or JSON string, got: {v}") from None
            if not isinstance(parsed, dict):
                raise ValueError(f"chain_configs must parse to a dict, got: {type(parsed)}") from None
            v = parsed
        # Validate each value is a non-empty string
        from aitbc.utils.chain_config import ChainConfigParser

        for chain_id, config_str in v.items():
            if not isinstance(config_str, str):
                raise ValueError(f"chain_configs['{chain_id}'] must be a string, got: {type(config_str)}")
            if config_str.strip():
                ChainConfigParser.parse(config_str)
        return v

    @field_validator("chain_sync_sources")
    @classmethod
    def validate_chain_sync_sources(cls, v: str) -> str:
        """Fail fast on malformed CHAIN_SYNC_SOURCES at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for pair in v.split(","):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid CHAIN_SYNC_SOURCES entry: '{pair}'. Expected 'chain_id:url'")
            chain_id, url = parts[0].strip(), parts[1].strip()
            if not chain_id or not url:
                raise ValueError(f"Invalid CHAIN_SYNC_SOURCES entry: '{pair}'. Empty chain_id or url")
            if chain_id in seen:
                raise ValueError(f"Duplicate chain_id in CHAIN_SYNC_SOURCES: '{chain_id}'")
            seen.add(chain_id)
        return v

    @field_validator("island_registry")
    @classmethod
    def validate_island_registry(cls, v: str) -> str:
        """Fail fast on malformed ISLAND_REGISTRY at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for entry in v.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 3:
                raise ValueError(f"Invalid ISLAND_REGISTRY entry: '{entry}'. Expected 'island_id:chain_id:hub_url'")
            island_id = parts[0].strip()
            if not island_id:
                raise ValueError(f"Invalid ISLAND_REGISTRY entry: '{entry}'. Empty island_id")
            if island_id in seen:
                raise ValueError(f"Duplicate island_id in ISLAND_REGISTRY: '{island_id}'")
            seen.add(island_id)
        return v

    @field_validator("gossip_backends")
    @classmethod
    def validate_gossip_backends(cls, v: str) -> str:
        """Fail fast on malformed GOSSIP_BACKENDS at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for entry in v.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GOSSIP_BACKENDS entry: '{entry}'. Expected 'chain_id:redis://url'")
            chain_id = parts[0].strip()
            if not chain_id:
                raise ValueError(f"Invalid GOSSIP_BACKENDS entry: '{entry}'. Empty chain_id")
            if chain_id in seen:
                raise ValueError(f"Duplicate chain_id in GOSSIP_BACKENDS: '{chain_id}'")
            seen.add(chain_id)
        return v

    @field_validator("bridge_islands")
    @classmethod
    def validate_bridge_islands(cls, v: str) -> str:
        """Validate bridge_islands CSV format: UUIDs only, no spaces, no empty entries (v0.6.3)."""
        if not v or not v.strip():
            return v
        islands = [i.strip() for i in v.split(",") if i.strip()]
        if len(islands) != len(set(islands)):
            raise ValueError(f"Duplicate island_id in bridge_islands: '{v}'")
        for island_id in islands:
            if " " in island_id:
                raise ValueError(f"Invalid bridge_islands entry: '{island_id}'. No spaces allowed (use UUID format)")
        return v

    max_reorg_depth: int = 10  # max blocks to reorg on conflict
    sync_validate_signatures: bool = True  # validate proposer signatures on import
    # ISO-8601 timestamp; if in the future, signature validation is temporarily disabled.
    sync_validate_signatures_skip_until: str = ""
    sync_state_root_validation_enabled: bool = True  # validate state roots on push/gossip block import

    # SyncManager settings (v0.11.0)
    sync_manager_enabled: bool = True  # master kill switch; when False no SyncManager is started
    sync_manager_use_gossip: bool = True
    sync_manager_use_subscription: bool = True
    sync_manager_poll_interval: float = 15.0
    sync_manager_block_dedup_ttl: float = 300.0
    sync_manager_block_dedup_max_size: int = 10000
    sync_manager_synced_poll_interval: float = 30.0
    sync_manager_state_sync_interval: float = 300.0
    sync_manager_max_proposal_gap: int = 2  # PBFT/PoA will not propose while gap is larger
    sync_manager_proposal_sync_timeout: int = 30  # seconds to wait for catch-up before skipping proposal
    sync_manager_http_enabled: bool = False  # optional in-process /sync/status HTTP server
    sync_manager_http_port: int = 8204
    sync_manager_http_host: str = "0.0.0.0"
    sync_parallel_peers: str = ""  # "url1,url2" or "chain_id:url1,..."
    state_sync_max_gap: int = 10
    block_scoped_preregistered_transactions: bool = (
        False  # apply pre-registered credit (BRIDGE_*) Account changes only at block time
    )

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
    gossip_websocket_url: str | None = None  # wss://host/rpc/gossip/ws for WebsocketGossipBackend
    # Mesh gossip (GOSSIP_BACKEND=mesh): comma-separated wss://<peer>/rpc/gossip/ws
    # URLs of every *other* validator. The local bus is gossip_broadcast_url.
    # Leave empty on RPC processes; only the node process should dial peers.
    gossip_mesh_peer_urls: str = ""
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
    hub_discovery_url: str = "hub.aitbc.invalid"  # Hub discovery DNS
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

    # Error retry interval for island background tasks (v0.6.3).
    island_task_error_retry_interval: int = 10

    # Bridge request expiry in seconds (v0.6.3).
    bridge_request_expiry: int = 3600

    # Island inactive threshold in seconds (v0.6.3).
    island_inactive_threshold: int = 600

    # Gossip topic migration (v0.6.3).
    gossip_tx_topic_v1: str = "transactions"
    gossip_tx_topic_v2_template: str = "transactions.{chain_id}"
    gossip_migration_days: int = 30
    gossip_log_v1_warnings: bool = True

    # Gossip websocket authentication and rate limiting (v0.7.6).
    gossip_auth_enabled: bool = os.getenv("GOSSIP_AUTH_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    gossip_auth_timeout: float = float(os.getenv("GOSSIP_AUTH_TIMEOUT", "5.0"))
    gossip_auth_challenge_ttl: float = float(os.getenv("GOSSIP_AUTH_CHALLENGE_TTL", "60.0"))
    gossip_max_message_size: int = int(os.getenv("GOSSIP_MAX_MESSAGE_SIZE", "1048576"))
    gossip_max_messages_per_minute: int = int(os.getenv("GOSSIP_MAX_MESSAGES_PER_MINUTE", "2000"))
    gossip_max_concurrent_connections_per_ip: int = int(os.getenv("GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP", "32"))

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
    # v0.10.16: fail-closed by default. The release path must be explicitly
    # enabled in production configuration after Merkle proof verification and
    # validator-set admission control are operational.
    bridge_release_enabled: bool = False

    # Operator pause switch for NEW bridge locks (BRIDGE_LOCKS_PAUSED). While
    # set, every lock-request surface — POST /bridge/lock, /bridge/batch/lock,
    # /swap and /cross-chain/bridge, plus the initiate_transfer chokepoint
    # itself — refuses new locks with HTTP 503; refunds, status reads and the
    # confirm path are untouched. In place pending the attestation-based
    # bridge validator set (the multisig confirm threshold is unreachable
    # while block headers carry only the proposer signature). A lock already
    # in the mempool still seals — gating admission would strand its funds
    # (BRIDGE_REFUND binds a *sealed* lock from v6).
    bridge_locks_paused: bool = False

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
    bridge_header_sync_batch: int = 500  # Max block headers mirrored into the bridge table per finalizer pass
    bridge_stuck_transfer_timeout: int = 3600  # Seconds before a pending transfer is flagged as stuck
    bridge_refund_delay_seconds: int = 0  # Minimum seconds after lock_time before a refund is allowed (0 = no delay)
    bridge_max_lock_amount: int = 0  # Maximum amount that can be locked in a single transfer (0 = unlimited)
    # GAP-47: in-process relayer. When True the bridge finalizer loop also
    # mirrors locally produced/synced block headers into bridge_block_header
    # and confirms pending transfers whose lock has reached finality (the
    # normal /rpc/bridge/confirm path — Merkle proof, header signature,
    # finality, multisig checks all still apply). It is AND-gated on
    # bridge_release_enabled in the finalizer loop, so this flag alone cannot
    # move value; disabling it turns the loop back into finalize-only.
    bridge_relayer_enabled: bool = True

    # GAP-47: cross-chain swap quote table. Comma-separated
    # "from_chain::to_chain=rate" or "chain:token::chain:token=rate" entries
    # the operator configures; swaps over pairs with no configured rate are
    # rejected unless both assets are identical (parity settlement at 1.0).
    # There is no cross-chain AMM to derive a price from, so the endpoint
    # refuses rather than inventing one.
    cross_chain_swap_rates: str = ""

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
    # v0.10.16: comma-separated list of Ethereum addresses authorized to register
    # bridge validators and ingest remote block headers. Empty means no admin is
    # configured, so validator/header admission is denied when the release fence
    # is enabled (fail-closed).
    bridge_admin_addresses: str = ""

    # Bridge verification configuration (v0.7.2). Replaces the trivially
    # forgeable field-equality proof validation with cryptographic Merkle
    # proof verification against stored block headers. The release fence
    # (bridge_release_enabled) is unfenced after this verification is
    # operational and tested.
    bridge_verification_mode: str = "in_process"  # "in_process" | "oracle"
    bridge_min_confirmations: int = 3  # minimum confirmations for any transfer
    bridge_finality_blocks: int = 6  # full finality threshold
    # Confirmations stop being counted at this depth (never below bridge_finality_blocks or
    # bridge_min_confirmations). Every new header used to bump every earlier header's count, a full
    # rewrite of bridge_block_header per block (22k rows, 12.5 MiB, ~3,200 WAL frames per block per node
    # on 2026-10-01, growing with chain height). Nothing decides on a count above the deepest requirement.
    bridge_confirmation_count_cap: int = 100
    bridge_large_transfer_threshold: int = 10000  # transfers above this require full finality
    # Production hardening: when True, _validate_proof REJECTS any proof that
    # does not carry a Merkle inclusion proof (merkle_proof + lock_event). The
    # default is False to preserve the v0.7.2 "field + signature" verification
    # mode used by isolated/dev networks; set BRIDGE_REQUIRE_MERKLE_PROOF=true
    # before enabling the release path on networks that move real value.
    bridge_require_merkle_proof: bool = False

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
    # for parallel tx validation (default: CPU count, capped at 16). CONFLICT_THRESHOLD is the fraction
    # of conflicting transactions above which the proposer falls back to
    # sequential validation (default 0.5 = 50%).
    parallel_tx_validation: bool = False  # Feature flag — default off for safety
    parallel_workers: int = max(2, min(16, os.cpu_count() or 4))  # Thread pool size for parallel tx validation
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
    gossip_priority_enabled: bool = True  # Enable message prioritization (v0.6.2) — enabled per v0.10.1

    # Parallel sync (v0.6.2). Feature flag for parallel block fetching
    # from multiple peers. Default off for safety — enable with
    # SYNC_PARALLEL_ENABLED=true. SYNC_PARALLEL_MAX_PEERS caps the number
    # of peers used concurrently for block range requests.
    # SYNC_PARALLEL_TIMEOUT is the per-peer request timeout in seconds.
    sync_parallel_enabled: bool = True  # Feature flag — enabled per v0.10.1 changelog
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
    sync_delta_enabled: bool = True  # Feature flag — enabled per v0.10.1 changelog
    sync_delta_threshold: float = 0.5  # Fall back to full sync if delta > 50% of state
    sync_delta_max_blocks: int = 100  # Max blocks for delta sync (use full sync above this)
    # Side-effect tables (stake, bond, governance_*) ride on state sync but are
    # written at RPC-submit time, before their tx seals — the delta cutoff
    # looks this far back from the range start so submit→seal lag and minor
    # clock skew cannot drop a row. SYNC_AUX_MAX_ROWS caps per-table rows in a
    # delta response; above it the peer falls back to a full snapshot.
    sync_aux_lookback_seconds: int = 900
    sync_aux_max_rows: int = 5000

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

    # Multi-validator consensus (v0.7.5). Master toggle for activating
    # MultiValidatorPoA + PBFT. When False, single-validator PoA remains
    # active. The RuntimeError guards in multi_validator_poa.py and pbft.py
    # read this setting.
    # v0.10.16 / G6: fail-closed by default. The single-proposer hub deployment must
    # not report itself as multi-validator. Enable only after explicit security review
    # and a validator_set has been configured.
    multi_validator_consensus_enabled: bool = False
    # Validator set: JSON list of {"address": "...", "stake": "1000"} objects.
    # Used by MultiValidatorPoA to select proposers and validate attestations.
    validator_set: str = ""
    # Validator keys controlled by this node: JSON mapping address -> private key.
    # May be set in blockchain-secrets.env. The mapping is used to sign blocks and
    # produce attestations. Keep this value out of the repository.
    validator_keys: str = ""
    # Minimum number of attestations required in block_metadata for a multi-validator
    # block to be accepted during sync (in addition to the proposer signature).
    # G6: require at least 2 validator attestations when multi-validator is active.
    # TRAP: this default is *nonzero*. Setting it explicitly to 0 or 1 LOWERS the
    # quorum bar below the shipped default — 0 does not mean "extra safe", it means
    # "no attestation certificate required". Do not set it without understanding
    # that larger is stricter, smaller is weaker.
    multi_validator_min_attestations: int = 2
    # v0.25.7: historical state-transition rule changes are gated by block version.
    # New blocks set state_transition_version=2 in their metadata. Blocks that
    # lack the version key are treated as v1 if their height is below this value
    # and as v2 at or above it. Default 0 means all unversioned blocks are v1,
    # so new chains with no history work under v2 from the first produced block.
    state_transition_v2_height: int = 0
    # S-4: per-escrow custody (v3) activation height. New blocks at or above this
    # height set state_transition_version=3. Default 0 means v3 is not activated;
    # existing chains continue under v2 until the operator sets a positive height.
    state_transition_v3_height: int = 0
    # GAP-42 remainder: consensus-enforced stake lock windows (v4). At or above
    # this height, STAKE_RELEASE txs must name their lock tx hashes and the
    # locks must have matured. Hardcoded rather than env-dependent because the
    # activation is itself consensus: an env-drifted fleet would fork. The
    # proposer stamps it into block_metadata and followers replay that stamp.
    state_transition_v4_height: int = 11000
    # Fail-closed authority gates (v5). At or above this height,
    # ESCROW_RELEASE/ESCROW_REFUND require a configured settlement authority,
    # GOVERNANCE_EXECUTE requires the governance_executors chain parameter, and
    # BRIDGE_RELEASE/BRIDGE_REFUND must carry the bridge pseudo-sender. Below it
    # the same checks stay lenient so sealed history replays. Hardcoded like
    # v4 — the activation is itself consensus — so keep it ahead of the chain
    # head until every fleet node runs a build that knows the rules.
    state_transition_v5_height: int = 24000
    # v6: a BRIDGE_REFUND must name the sealed BRIDGE_LOCK it repays on the same
    # chain (payload.lock_tx_hash, sender/amount match, not already refunded).
    # Below it refunds stay lenient for replay. Unlike v5 this is env-gated
    # (STATE_TRANSITION_V6_HEIGHT) rather than baked — set it uniformly on
    # every node once the fleet runs a build that enforces it; fleet-config-check
    # watches for drift. 0 disables the gate.
    state_transition_v6_height: int = 0
    # v7: a GPU_REGISTER for an existing gpu_id must come from the registrant
    # recorded on that row (registered_by = the first registrant's tx sender).
    # Below it any funded account could overwrite another provider's GPU
    # registration; replay keeps that lenient behavior. Activated fleet-wide
    # at block 24650 on 2026-09-26 and verified across a full proposer
    # rotation, so the height is now consensus and is hardcoded like v4/v5 —
    # a lost env file must not re-open the overwrite rule.
    state_transition_v7_height: int = 24650
    # v8: stamped-version integrity. At or above this height a block's
    # recorded block_metadata.state_transition_version becomes advisory —
    # validation always uses the height-derived version, and a mismatched or
    # missing stamp is logged + counted (block_version_stamp_mismatch_total)
    # rather than obeyed or rejected. block_metadata is covered by neither
    # the block hash nor the proposer signature, so trusting the stamp would
    # let any relay pick the rules a block is validated under. Below this
    # height the stamp stays proposer-controlled and trusted (pre-v8
    # semantics); the fleet audit showed every recorded stamp matches its
    # height-derived version, so no historical block is affected. Activated
    # fleet-wide at block 24800 on 2026-09-26 and proven over a full
    # rotation plus node0's range-sync import, so the height is now
    # consensus and hardcoded like v4/v5/v7 — a lost env file must not
    # silently return a node to trusting the recorded stamp.
    state_transition_v8_height: int = 24800
    # v9: transaction authorization. At or above this height every
    # user-originated transaction must carry a valid sender signature at
    # apply time (V9_UNSIGNED_ALLOWED_TX_TYPES in state/v9_policy.py are
    # the only unsigned exceptions, each with its own authority check),
    # served block transactions carry the stored signed envelope, and
    # attesters verify tx signatures + nonce order against their own
    # parent state before signing. None means v9 is NOT activated: the
    # same rules still evaluate in shadow mode — every would-reject logs
    # and counts v9_would_reject_*_total instead of rejecting, so the
    # allowlist can be proven complete against live traffic. Activated
    # fleet-wide at block 30400 on 2026-09-30 after a >24h clean shadow
    # window and a nine-type canary sweep with zero substantive
    # v9_would_reject counters, so the height is now consensus and is
    # hardcoded like v4/v5/v7/v8.
    state_transition_v9_height: int | None = 30400
    # v10: GPU_DEREGISTER. At or above this height the registrant of a gpu_registration row can set it to
    # ``deactivated`` with a signed GPU_DEREGISTER; GPU_ALLOCATE against a deactivated row is refused. Below
    # it the type name has no consensus meaning at all and a block carrying it replays exactly as before (a
    # plain value transfer), so sealed history is untouched; None still disables it the same way. Every
    # validator and follower must run a build that knows the type BEFORE this height: an older build leaves
    # the row ``active`` and would accept a later GPU_ALLOCATE the new rules refuse. Activated fleet-wide
    # at block 32100 on 2026-10-02, proven over a full proposer rotation and the first live GPU_REGISTER /
    # GPU_DEREGISTER sealed under it (blocks 32803/32804), so the height is now consensus and is hardcoded
    # like v4 to v9. An environment value (STATE_TRANSITION_V10_HEIGHT) still overrides this default.
    # fleet-config-check watches for drift.
    state_transition_v10_height: int | None = 32100
    # v11: ESCROW_FEE_SWEEP. At or above this height the settlement authority may sweep a settled escrow's
    # custody residue — the withheld platform fee plus rounding dust that v3 custody strands in the
    # per-escrow account — to the recipient pinned by the on-chain ``escrow_fee_recipient`` chain parameter
    # (env fallback ESCROW_FEE_RECIPIENT, unset fails closed). Apply-time rules: payload.job_id names the
    # custody account, sender must equal ``escrow_settlement_authority`` resolved at apply height, recipient
    # must equal the resolved fee recipient, and value is bounded only by the custody balance — the same
    # trust bound the authority already holds over each release's amount. Below this height the type name
    # has no consensus meaning at all and a block carrying it replays exactly as before (a plain value
    # transfer), so sealed history is untouched; None still disables it the same way. Every validator and
    # follower must run a build that knows the type BEFORE this height: an older build would apply a sealed
    # sweep as a plain transfer and diverge. Activated fleet-wide at block 35400 on 2026-10-05 — all five
    # hosts agreed on the transition block's hash and production continued cleanly past it — so the height
    # is now consensus and is hardcoded like v4 to v10. An environment value (STATE_TRANSITION_V11_HEIGHT)
    # still overrides this default. fleet-config-check watches for drift.
    state_transition_v11_height: int | None = 35400
    # v12: authority-parameter value checks. At or above this height a GOVERNANCE_EXECUTE ``parameter_change``
    # to one of the five authority chain parameters (governance_executors, bond_slash_authority,
    # bridge_release_authority, escrow_settlement_authority, escrow_fee_recipient) must carry a well-formed
    # value: non-empty, every comma-separated element a canonical 0x+40-hex address, no zero address, no
    # duplicates after canonicalisation, at most one element for the four single-address parameters, and —
    # for governance_executors — at least one member holding the baked executor minimum (DEFAULT_TX_FEE_UNITS,
    # the lowest balance that can pay a fee; decided as a constant, not the tx's fee, because consensus has no
    # minimum fee). Below the height a malformed value seals exactly as before (B9: a typo'd, empty or
    # never-funded executor list seals and freezes all parameters), so sealed history is untouched; None still
    # disables it the same way. Every validator and follower must run a build that enforces the checks BEFORE
    # this height: an older build would seal a transaction the fleet rejects and diverge. Activated fleet-wide
    # at block 37500 — STATE_TRANSITION_V12_HEIGHT=37500 was set on all five hosts and block 37500 stamped
    # version 12 — so the height is now consensus and is hardcoded like v4 to v11. An environment value
    # (STATE_TRANSITION_V12_HEIGHT) still overrides this default. fleet-config-check watches for drift.
    state_transition_v12_height: int | None = 37500
    # Comma-separated ``gpu_id``s that GPU_REGISTER and GPU_ALLOCATE may not name (env ``GPU_RETIRED_IDS``). Empty
    # (the default) refuses nothing. Admission only: it is a door check on this node's REST, gossip and p2p intake,
    # not a consensus rule, so a block from a validator that does not set it still applies such a transaction. Its
    # purpose is to keep the ids retired on 2 Oct 2026 (scripts/ops/gpu-registry-sweep.py lists them) from being
    # registered again by anyone; it does not change what a replay of sealed history produces.
    gpu_retired_ids: str = ""
    # S-4: address allowed to sign ESCROW_RELEASE and ESCROW_REFUND on v3+.
    # The on-chain escrow_settlement_authority chain parameter takes precedence;
    # this setting (or ESCROW_RELEASE_ADDRESS) is the fallback for chains that
    # never set it. Below v5 an unset authority disables the check (legacy);
    # from state_transition_v5_height the transition fails closed instead.
    escrow_settlement_authority: str = ""
    # v11: ESCROW_FEE_SWEEP must pay this recipient — the treasury account that
    # collects the residue v3 custody strands in each per-escrow account.
    # The on-chain escrow_fee_recipient chain parameter takes precedence; this
    # setting (or ESCROW_FEE_RECIPIENT env) is the fallback for chains that
    # never set it. Unset fails closed: the sweep is refused, never misdirected.
    escrow_fee_recipient: str = ""
    # v5: BRIDGE_RELEASE/BRIDGE_REFUND must carry a secp256k1 signature over
    # the credit's semantic fields that recovers to this authority. The
    # on-chain bridge_release_authority chain parameter takes precedence; this
    # setting (or BRIDGE_RELEASE_AUTHORITY env) is the fallback, then the
    # escrow settlement authority — the bridge service signs credits with the
    # same operator settlement key unless told otherwise.
    bridge_release_authority: str = ""
    # Optional dedicated key (BRIDGE_RELEASE_PRIVATE_KEY env) used by the
    # bridge service to sign issued credits. Falls back to
    # ESCROW_RELEASE_PRIVATE_KEY, which the RPC process already holds.
    bridge_release_private_key: str = ""
    # Seconds to wait for remote attestation responses over gossip when this node is the proposer.
    multi_validator_attestation_timeout_seconds: float = 1.0
    # After the attestation quorum is reached, keep collecting this many extra
    # seconds so slower-but-valid validators still land in the block instead of
    # losing the first-to-min_count race every round. 0 keeps the old
    # seal-as-soon-as-quorum behaviour. Bounded by the timeout above.
    attestation_post_quorum_linger_seconds: float = 0.0
    # v0.18.0: reject unsigned PBFT messages by default; test harnesses must
    # set this to False explicitly.
    pbft_require_signatures: bool = True
    # v0.7.6 PBFT master toggle. When True, block production runs the full
    # pre-prepare / prepare / commit phases before a block is committed.
    # Fail-closed by default; requires at least 4 validators for f=1 BFT.
    pbft_consensus_enabled: bool = False
    # View-change timeout used by PBFT consensus (seconds).
    pbft_view_change_timeout: int = 30
    consensus_view_change_timeout_seconds: int = 30  # H6 — timeout before view change
    consensus_round_timeout_seconds: int = 10  # per-round timeout
    # v0.25.6: deterministic proposer rotation. When the scheduled proposer for
    # a height does not produce a block, the round derived from the parent
    # block's timestamp advances and the next validator in the round-robin
    # takes the slot. Every node derives the same round from on-chain
    # timestamps, so an unavailable proposer is routed around without any
    # view-change message exchange. Set it comfortably larger than the largest
    # gap the network produces when it is healthy. A smaller value is still
    # safe, because the proposer derives the round from the same timestamp its
    # validators will, but the slot then rotates on ordinary blocks instead of
    # only when a proposer is missing. The default aligns with the heartbeat
    # interval so a silent proposer is skipped within one heartbeat cycle.
    # Left unset, this is derived from ``max_empty_block_interval`` -- see
    # ``_scale_the_proposer_round_to_the_heartbeat``. An explicit value wins.
    consensus_proposer_round_seconds: int = 60
    # v0.25.x attester lock: a validator that signs (attests) a peer's block
    # at height h will not propose — or re-attest — a different block at h
    # for one proposer round. Instead it tries to fetch the attested block
    # from a mesh peer and pull it. The lock expires after one round window
    # so an attested block that never materialises cannot stall production.
    attestation_lock_enabled: bool = True
    # Delta-journal undo for non-empty losing fork segments
    # (``state/block_deltas.py``). While False the resolvers escalate a
    # non-empty segment to the operator exactly as before the journal
    # existed — the journal still records, but nothing is reverted. Default
    # on: the journal is fail-closed (any capture gap stamps an ``incomplete``
    # sentinel and revert refuses the block) and per-family differential
    # tests prove apply+revert restores every chain table. The ancestor
    # state-root check remains as a second net for the ``account`` table.
    sync_fork_undo_enabled: bool = True
    # Drop a pre-prepare whose sender is not the scheduled proposer for the
    # block's height and round. Setting this False restores the pre-v0.25.6
    # behaviour, where any validator's proposal was prepared.
    consensus_enforce_proposer_schedule: bool = True
    # Pre-proposal freshness gate: before building a block, compare the local
    # head with every GOSSIP_MESH_PEER_URLS peer's /rpc/head. A peer ahead (or
    # disagreeing at our height) blocks the proposal; per-peer query timeout
    # bounds the added latency and unreachable peers degrade to UNVERIFIED
    # (propose anyway, metric recorded) rather than halting the chain.
    proposal_freshness_check_enabled: bool = True
    proposal_freshness_peer_timeout_seconds: float = 2.0
    # A cached freshness verdict is only valid this long — far below the round
    # window, so a "fresh" verdict can never survive into a later round after a
    # network blip. UNVERIFIED results are never cached at all.
    proposal_freshness_cache_ttl_seconds: float = 5.0
    # An ahead peer whose bulk pull finishes without moving our head is dropped
    # from the ahead check for this long (~10 round windows): its taller fork
    # would otherwise silence us forever. Hash votes are unaffected.
    proposal_freshness_peer_quarantine_seconds: float = 600.0
    consensus_validator_set_epoch_blocks: int = 7200  # C3 — epoch length for rotation
    consensus_slashing_enabled: bool = True  # C2 — enable slashing
    consensus_slashing_amount: Decimal = Decimal("100.0")  # stake to slash per offense
    consensus_byzantine_threshold: int = 3  # slash count before deactivation

    # Cross-chain settlement (v0.9.0). Atomic settlement uses HTLCs to
    # ensure either both chains settle or both refund. Settlement RPC
    # endpoints and CrossChainSettlementService are now active; B4 (HTLC
    # contract integration) is complete. Enabled by default for the homebrew
    # network — operators can still disable explicitly if they run a private
    # deployment before a security review.
    escrow_enabled: bool = True
    escrow_atomic_settlement: bool = True  # use HTLC (vs manual admin refund)
    escrow_timeout_default: int = 3600  # 1 hour default timeout
    escrow_timeout_large: int = 86400  # 24 hours for large trades
    escrow_timeout_extension_max: int = 604800  # 7 days max extension
    escrow_htlc_enabled: bool = True  # use HTLC contract for escrow
    escrow_htlc_contract_address: str = ""  # deployed CrossChainAtomicSwap.sol
    escrow_large_trade_threshold: int = 10000  # trades above this use large timeout

    @model_validator(mode="after")
    def _scale_the_proposer_round_to_the_heartbeat(self) -> ChainSettings:
        """Size the round window from the heartbeat unless it was set explicitly.

        The window has to clear the longest gap a healthy network leaves
        between blocks, or an ordinary late block is attributed to the next
        round and its proposer is skipped. That gap is set by
        ``max_empty_block_interval``, so a constant here and a per-deployment
        heartbeat there are free to drift apart -- and had: 300s against the
        deployed 60s heartbeat, on a chain measured producing a block every
        62-72s, meant a validator going dark cost five minutes on every height
        it owned. Aligning the round with the heartbeat (rather than 2x) means
        a silent proposer is skipped within one heartbeat cycle instead of two.
        """
        if "consensus_proposer_round_seconds" not in self.model_fields_set:
            # Align the round window with the heartbeat interval, not 2x it.
            # The C-2 live exercise found that a 120s round vs 60s heartbeat
            # stalls the chain for 2 full heartbeats when a proposer is silent,
            # because the round does not advance until 120s but the heartbeat
            # fires at 60s — and the heartbeat cannot be produced because the
            # round-0 proposer is the one that is dead. Setting the round to
            # the heartbeat interval means the round advances at the same
            # moment the heartbeat would fire, handing the slot to the next
            # validator within one heartbeat cycle.
            self.consensus_proposer_round_seconds = max(30, self.max_empty_block_interval)
        return self

    @model_validator(mode="after")
    def _resolve_validate_signatures(self) -> ChainSettings:
        """If SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL is a future timestamp, disable validation.

        Both outcomes are logged. Turning proposer-signature validation off is a
        security-relevant change that used to happen silently, so a stale value
        left over from a past migration was invisible; a malformed value fails
        closed, which is the safe direction but is just as easy to miss.

        In production the kill-switch is additionally horizon-limited: a
        skip-until more than 48h out is almost certainly an operator mistake
        or a leftover from a long-forgotten incident, so the node refuses to
        start rather than run with signature validation off indefinitely.
        """
        if not self.sync_validate_signatures or not self.sync_validate_signatures_skip_until:
            return self
        # Imported locally: this validator runs while the module is still being
        # imported, before aitbc_chain.logger can be safely pulled in.
        import logging

        from aitbc.utils.env import is_production

        logger = logging.getLogger(__name__)
        try:
            from datetime import UTC, datetime, timedelta

            skip_until = datetime.fromisoformat(self.sync_validate_signatures_skip_until)
            # Naive timestamps are read as UTC — a naive/aware comparison would
            # otherwise raise TypeError outside the ValueError guard below.
            if skip_until.tzinfo is None:
                skip_until = skip_until.replace(tzinfo=UTC)
        except ValueError:
            logger.warning(
                "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=%r is not a valid ISO timestamp; "
                "leaving block proposer signature validation ENABLED",
                self.sync_validate_signatures_skip_until,
            )
            return self
        if datetime.now(UTC) >= skip_until:
            return self
        horizon = skip_until - datetime.now(UTC)
        if is_production() and horizon > timedelta(hours=48):
            raise ValueError(
                "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL="
                f"{self.sync_validate_signatures_skip_until} disables block proposer signature "
                f"validation for {horizon.days} days; production nodes may skip at most 48h"
            )
        self.sync_validate_signatures = False
        logger.warning(
            "Block proposer signature validation is DISABLED by "
            "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=%s; it re-enables itself after that time",
            self.sync_validate_signatures_skip_until,
        )
        return self

    def mesh_peer_url_list(self) -> list[str]:
        """Parsed ``GOSSIP_MESH_PEER_URLS`` (empty entries dropped)."""
        return [u.strip() for u in self.gossip_mesh_peer_urls.split(",") if u.strip()]

    def gpu_retired_id_set(self) -> frozenset[str]:
        """Parsed ``GPU_RETIRED_IDS`` (empty entries dropped)."""
        return frozenset(i.strip() for i in self.gpu_retired_ids.split(",") if i.strip())


settings = ChainSettings()


def is_block_producer(cfg: ChainSettings = settings) -> bool:
    """Whether this node produces blocks — hub mode or a configured PBFT validator.

    Producers derive state by applying blocks; follower state sync must never
    overwrite their account table (incident 27207, 2026-09-28). Same predicate
    as main.py's "Running as block producer" gate.
    """
    return cfg.blockchain_mode == "hub" or bool(
        cfg.multi_validator_consensus_enabled and cfg.validator_set and cfg.proposer_id and cfg.proposer_key
    )
