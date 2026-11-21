from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from aitbc.constants import DATA_DIR


class NodeConfig(BaseModel):
    # Node profiles (set during setup.sh)
    blockchain_mode: str = "follower"  # follower or hub
    market_role: str = "customer"  # customer or shop
    hardware_profile: str = "nogpu"  # gpu or nogpu

    chain_id: str = ""
    supported_chains: str = ""  # Comma-separated list of supported chain IDs (defaults to chain_id if empty)
    db_path: Path = DATA_DIR / "data" / "chain.db"
    db_encryption_enabled: bool = False  # Phase 2: SQLCipher database encryption flag (applies to the configured chain)
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
    # #1265: verify chain.db via PRAGMA quick_check at init_db() (fail-fast)
    # and periodically during runtime (alert-and-quarantine: a corrupt chain
    # refuses block import, block proposal, and attestation signing).
    db_integrity_check_enabled: bool = True
    db_integrity_check_interval_seconds: float = 60.0
    # #2205: the node process writes its metrics_registry to DATA_DIR/node_metrics.prom
    # every interval so the RPC /metrics can show consensus counters that live in the
    # node process (separate registry). No port; staleness <= one interval.
    node_metrics_snapshot_enabled: bool = True
    node_metrics_snapshot_interval_seconds: float = 5.0
    # #1615 CHAINDB-FK-ENFORCE-1: enforce declared FOREIGN KEY constraints on
    # every chain.db connection (PRAGMA foreign_keys=ON in _set_sqlite_pragmas).
    # Default OFF pending the escrow write-path audit: the Escrow row is
    # persisted when the lock is admitted — before the provider's Account row
    # exists (provider accounts are materialized at block apply for v2+ locks,
    # and only then) — so blanket enforcement would fail escrow creation for
    # first-time providers. A PRAGMA foreign_key_check scan of the live bc-2
    # store found zero violations, so existing data is clean; the risk is
    # write ordering, not data.
    db_foreign_keys_enabled: bool = False
    # #1616 CHAINDB-VACUUM-1: bounded freelist reclaim, run once per db
    # integrity sweep per chain. Only databases created after this change
    # carry auto_vacuum=INCREMENTAL (set in _set_sqlite_pragmas before
    # create_all); existing stores keep auto_vacuum=NONE, where
    # incremental_vacuum is a no-op — reclaiming those needs a one-time
    # offline VACUUM. The pass also publishes chain_db_page_count /
    # chain_db_freelist_pages gauges so growth stays visible. 0 disables the
    # vacuum (the gauges still run).
    db_incremental_vacuum_max_pages: int = 500

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

    # CORS configuration
    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if os.getenv("CORS_ORIGINS")
        else ["http://localhost:3000"]
    )

    # Loopback by default (#1871): the RPC surface is reached through nginx
    # or co-located services; a deployment that deliberately exposes it
    # sets RPC_BIND_HOST in its env file.
    rpc_bind_host: str = "127.0.0.1"
    rpc_bind_port: int = 8202

    # Loopback by default as well: the only live consumer is the
    # hub-internal gossip relay (its wrapper already defaults 127.0.0.1,
    # #1065) and the advertised-endpoint calc treats loopback like
    # bind-all. The dormant TCP mesh (p2p_network.py) can widen via env if
    # it is ever re-enabled.
    p2p_bind_host: str = "127.0.0.1"
    p2p_bind_port: int = 8200
    p2p_node_id: str = ""
    # Dormant TCP-mesh hardening bounds (#1630/#1631). p2p_network.py is not
    # deployed (aitbc-blockchain-p2p runs gossip.relay), but its docstring
    # requires admission parity if it is ever re-enabled — these caps bound
    # inbound connections (total + per source IP), the post-handshake read
    # loop (silence timeout = dead-peer reap), and per-peer message rate.
    p2p_max_connections: int = 64
    p2p_max_connections_per_ip: int = 8
    p2p_stream_read_timeout_seconds: float = 300.0
    p2p_peer_messages_per_second: float = 100.0

    contact_email: str = os.getenv("CONTACT_EMAIL", "operator@aitbc.invalid")

    proposer_id: str = ""
    proposer_key: str | None = None

    # Treasury key (legacy GENESIS_* env names) used for governance execution,
    # fee subsidies, and other chain-level operations. Preferably loaded from node.env / secrets.
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
    # Orphan tx-only lock refund pass (#2380): sw_job_* ESCROW_LOCKs carry no
    # job/escrow row, so no other pass sees them. A lock older than the min
    # age with no settlement leg gets a full buyer refund. The floor is
    # max(state_transition_v3_height, escrow_fee_sweep_pass_min_height).
    escrow_orphan_refund_pass_min_age_seconds: int = 21600
    escrow_orphan_refund_pass_max_jobs: int = 25
    # How many nonces ahead of the account nonce a pending transaction may sit.
    # Admission rejects beyond this so one sender cannot queue an unbounded
    # pipeline of not-yet-executable transactions.
    mempool_nonce_lookahead: int = 16
    # #1300 P2-v2.4: PostgreSQL lock/statement timeout (ms) applied via
    # SET LOCAL inside mempool admission transactions before advisory-lock
    # acquisition. A hashtext collision or stuck lock surfaces as a typed
    # MempoolAdmissionTimeout, never a raw OperationalError.
    mempool_admission_lock_timeout_ms: int = 5000
    # #1300 P2-v2.4: owner/epoch reservation drain (peek_reserve). OFF by
    # default — the legacy delete-on-read drain() stays authoritative until
    # an operator arms this after the S3 parity legs.
    mempool_reservation_enabled: bool = False
    # #2193 F2: release chain.db's write lock while the proposer waits for the
    # PBFT/attestation gates, then re-apply and require a byte-identical block
    # hash before committing. Local scheduling only (the sealed block is
    # unchanged), so no consensus height gate. OFF by default; armed per host.
    proposer_release_write_lock_during_gates: bool = False
    # Reservation TTL is derived by the caller from attempt-time config
    # (collect deadline + apply budget + gate timeouts + commit bound +
    # broadcast reconcile bound); this is only the fallback when a caller
    # does not supply one.
    mempool_reservation_ttl_seconds: int = 120

    # Circuit breaker
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: int = 30  # seconds before half-open

    # Sync settings
    trusted_proposers: str = ""  # comma-separated list of trusted proposer IDs
