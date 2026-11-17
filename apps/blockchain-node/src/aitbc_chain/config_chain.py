from __future__ import annotations

import os

from pydantic import BaseModel

from .config_env import DEFAULT_ISLAND_ID


class SyncConfig(BaseModel):
    max_reorg_depth: int = 10  # max blocks to reorg on conflict
    # eth_getLogs budgets (RPC-GETLOGS-UNBOUNDED-1): the route is public, so the
    # scan is bounded whatever the request holds — span in blocks, receipt rows
    # bound in SQL, returned log entries. Deeper windows paginate by range.
    getlogs_max_block_span: int = 2000
    getlogs_max_receipts: int = 5000
    getlogs_max_logs: int = 1000
    # /rpc/blocks-range span budget: the route feeds peer bulk sync (batches
    # are <= max_bulk_sync_batch_size) but is otherwise public — an
    # unbounded start/end used to serialize the entire chain plus every
    # transaction envelope in one response. Wider windows paginate.
    blocks_range_max_span: int = 10_000
    # /rpc/transactions/market/match and /rpc/market/listings scan confirmed
    # GPU_MARKET rows to derive listings; bound the candidate window to the
    # newest N rows so cost cannot grow with total market history (#1511).
    # A cancel/replaces older than the window can no longer hide an in-window
    # listing — accepted trade-off, the window is generous.
    market_scan_max_rows: int = 10_000
    sync_validate_signatures: bool = True  # validate proposer signatures on import
    # ISO-8601 timestamp; if in the future, signature validation is temporarily disabled.
    sync_validate_signatures_skip_until: str = ""
    sync_state_root_validation_enabled: bool = True  # validate state roots on push/gossip block import
    # #1325 option (e): from this height on, a block that arrives without a state_root is
    # refused at import instead of skipping the root comparison. None = off (legacy:
    # an empty root bypasses the check). Apply-time rule: arm it fleet-wide at a height
    # every validator already runs, never mid-history.
    sync_require_state_root_height: int | None = None

    # SyncManager settings (v0.11.0)
    # #1814: refuse to start when a bond escrow/burn account the env names is missing from a chain that
    # already has blocks (env disagrees with the chain). False = log + metric only.
    startup_account_check_strict: bool = True
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
    # TEST-ONLY when false — construction refuses env-bound False (see the
    # validator above); the non-block-scoped path mutates committed tables
    # outside block apply and exists only for tests patching the attribute.
    block_scoped_preregistered_transactions: bool = (
        True  # apply pre-registered credit (BRIDGE_*) Account changes only at block time
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
    # Upper bound for a client-requested lease duration on /rpc/subscribe and
    # /rpc/heartbeat (#1703): without it a peer-key holder could pin an
    # effectively eternal lease (or 500 the route with a non-numeric value).
    subscription_max_lease_duration: int = 86400  # 24 hours
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
    # #1701 (default OFF): dedup mesh messages per subscription instead of
    # backend-wide, so a second subscriber to the same topic (the persistent
    # attest_response observer armed by vote_journal_justification_enabled)
    # cannot swallow the messages another subscriber (the collector) needs.
    gossip_mesh_dedup_per_subscription: bool = False
    # #1711: node-engine readiness heartbeat. The consensus engine
    # (aitbc_chain.main) has no HTTP surface, so it writes this JSON file on
    # an interval; the RPC /ready probe fails while the file is missing,
    # stale, or reports a non-ready component. Empty disables both sides.
    node_engine_ready_file: str = ""
    node_engine_ready_interval_seconds: float = 15.0
    node_engine_ready_max_age_seconds: float = 45.0
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
    # Scoped (payload-bound) gossip signatures (#1128). Off while the fleet
    # rolls out: unscoped signatures are still accepted so old and new nodes
    # keep gossiping mid-restart. Flip on only after every host is on the new
    # build — per the issue, the flip is a separate planned step.
    gossip_auth_require_scope: bool = os.getenv("GOSSIP_AUTH_REQUIRE_SCOPE", "false").lower() in ("1", "true", "yes")
    # Chain-bound gossip scopes (#1159): channel_scope always includes the
    # resolved chain_id; while this is off, signatures made against the
    # legacy chain-less scope are still accepted so old and new nodes keep
    # gossiping mid-rollout. Flip on only after every dialer signs the
    # chain-bound scope — the flip is a separate planned step (Phase B gate).
    gossip_auth_require_chain_scope: bool = os.getenv("GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    # Per-chain validator membership guard (#1259, D2 option P). The validator
    # set is process-global (``VALIDATOR_SET``), so on a process that connectably
    # serves a NON-default chain a validator of the default chain could pass the
    # membership check on that chain. While this flag is off the situation is
    # only counted (``gossip_auth_membership_unconfigured_total``); on, such
    # connections are refused (1008, reason ``chain_membership_unconfigured``)
    # unless the chain is listed in ``GOSSIP_SHARED_VALIDATOR_CHAINS``.
    # Single-chain hosts are unaffected either way. Counter-first rollout.
    gossip_auth_require_chain_membership: bool = os.getenv("GOSSIP_AUTH_REQUIRE_CHAIN_MEMBERSHIP", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    gossip_shared_validator_chains: str = os.getenv("GOSSIP_SHARED_VALIDATOR_CHAINS", "")
    # Dialer side of the same rollout (#1255, #1159 design v2 D1): what THIS
    # node signs when it dials a peer. Split from ``..._require_chain_scope``
    # (server strictness) so the flip is staged: sign=on fleet-wide first
    # (servers still accept both), watch ``gossip_auth_legacy_scope_accepted_total``
    # stay at 0, then require=on. A host with require=on always signs the
    # chain-bound scope too (see ``WebsocketGossipBackend._auth_scope``) -
    # signing legacy to require-on peers would only get rejected.
    gossip_auth_sign_chain_scope: bool = os.getenv("GOSSIP_AUTH_SIGN_CHAIN_SCOPE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    gossip_max_message_size: int = int(os.getenv("GOSSIP_MAX_MESSAGE_SIZE", "1048576"))
    # #1874: public gossip topics (transactions/status/mempool) are
    # subscribe-open but publish-gated — a peer_auth frame carrying the
    # node's BLOCKCHAIN_RPC_API_KEY (fleet key, configured peer key, or
    # issued join key) is required before a publish is bridged to the
    # broker. Only meaningful while gossip_auth_enabled is on; off restores
    # the pre-#1874 open-publish behaviour as an escape hatch.
    gossip_public_publish_require_key: bool = os.getenv("GOSSIP_PUBLIC_PUBLISH_REQUIRE_KEY", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    # #1306: make broadcast-backend subscribe() wait until the redis SUBSCRIBE is live,
    # so a request published right after subscribing cannot lose fast responses.
    gossip_subscribe_wait_ready_enabled: bool = False
    gossip_subscribe_ready_timeout_seconds: float = 2.0
    # #1764: mesh-backend subscribe() can wait until peer websocket legs are
    # attached, so a round that publishes right after subscribing does not miss
    # fast attest_response messages while _retry_attach is in backoff.
    gossip_mesh_subscribe_wait_peers_enabled: bool = os.getenv("GOSSIP_MESH_SUBSCRIBE_WAIT_PEERS", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    gossip_mesh_subscribe_wait_peers_timeout_seconds: float = float(
        os.getenv("GOSSIP_MESH_SUBSCRIBE_WAIT_PEERS_TIMEOUT", "2.0")
    )
    # #2109: restrict the #1764 wait to topics starting with one of these
    # comma-separated prefixes (e.g. "consensus.attest_response."), so a trial
    # does not delay every other subscribe. Empty (default) = the flag applies
    # to all topics, as before. Has no effect unless the flag above is on.
    gossip_mesh_subscribe_wait_peers_topics: str = os.getenv("GOSSIP_MESH_SUBSCRIBE_WAIT_PEERS_TOPICS", "")
    gossip_max_messages_per_minute: int = int(os.getenv("GOSSIP_MAX_MESSAGES_PER_MINUTE", "2000"))
    # Body-size cap for POST /gossip on the standalone relay unit
    # (aitbc-blockchain-p2p, aitbc_chain.gossip.relay) — #1591. The ws gossip
    # path caps each message at gossip_max_message_size; the HTTP publish
    # path had no bound at all. 4 MiB covers a max-size block/message plus
    # auth fields with headroom.
    gossip_relay_max_body_bytes: int = int(os.getenv("GOSSIP_RELAY_MAX_BODY_BYTES", "4194304"))
    gossip_max_concurrent_connections_per_ip: int = int(os.getenv("GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP", "32"))
    # Aggregate per-source-IP ceilings ACROSS every chain this host serves
    # (#1257, #1159 design v2 D3). The per-chain limits above multiply with the
    # number of served chains (K x 32 connections, K x 5 x 2000 msg/min per IP);
    # these cap the sum. 0 = disabled (default), so a single-chain host behaves
    # exactly as before.
    gossip_max_connections_per_ip_total: int = int(os.getenv("GOSSIP_MAX_CONNECTIONS_PER_IP_TOTAL", "0"))
    gossip_max_messages_per_minute_total: int = int(os.getenv("GOSSIP_MAX_MESSAGES_PER_MINUTE_TOTAL", "0"))
    # Per-source-IP cap on /rpc/subscribe/ws block-push connections (#1587):
    # the endpoint accepted unlimited sockets per IP, each holding a broker
    # subscription and two forwarder tasks. 8 covers a follower running
    # several chains plus reconnect overlap.
    subscribe_ws_max_connections_per_ip: int = int(os.getenv("SUBSCRIBE_WS_MAX_CONNECTIONS_PER_IP", "8"))

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
