from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from .config_env import KEYSTORE_DIR


class InfraConfig(BaseModel):
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
    # SYNC_AUX_MAX_PAYLOAD_BYTES bounds the serialized size of the whole
    # aux_state object a sync SOURCE ships us (#1628): aux tables sit outside
    # the account state root, so ingest-side caps are the only pre-commit
    # bound on a hostile or broken peer payload. 64 MiB matches
    # sync_state_diff_max_bytes — far above any legitimate aux payload.
    sync_aux_lookback_seconds: int = 900
    sync_aux_max_rows: int = 5000
    # Row cap for the peer-supplied chain_parameters / chain_parameter_history
    # lists on both sync paths (#1628): like aux_state they sit outside the
    # account state root, so ingest-side bounds are the only pre-commit
    # limit. Legitimate lists are governance keys plus one history row per
    # change — 10k per list is far above any real chain.
    sync_params_max_rows: int = 10_000
    sync_aux_max_payload_bytes: int = 67_108_864
    # Decompressed-size cap for a peer-supplied state diff (#1627): the delta
    # endpoint's payload is decoded before the state-root check runs, so the
    # bound has to live at decompress time or a compressed bomb OOMs first.
    # 64 MiB is ~650k account changes at the ~100-byte/change estimate — far
    # above any legitimate delta (threshold already falls back at 50% of state).
    sync_state_diff_max_bytes: int = 67_108_864
    # Decompressed-size cap for the whole JSON body of a peer-supplied
    # /rpc/state/snapshot or /rpc/state/delta response (#1627 remainder):
    # httpx buffers and transparently decodes the body, so the cap has to
    # live at streamed-read time. 256 MiB covers the largest legitimate
    # payload — a full snapshot (all accounts + aux_state up to
    # sync_aux_max_payload_bytes) or a delta (base64 diff up to ~90 MiB +
    # params + aux) — while still bounding a hostile peer's memory cost.
    sync_state_response_max_bytes: int = 268_435_456
    # Account-row cap for peer-supplied snapshot lists and delta change sets
    # (#1594): ``sync_state_response_max_bytes`` bounds wire size, but a dense
    # JSON array can still enumerate millions of tiny rows — refuse before any
    # ORM object is materialized. Set far above any production chain.
    sync_state_max_accounts: int = 2_000_000
    # Decompressed-size cap for /rpc/blocks-range bodies the bulk-sync client
    # reads (#1594): the serve-side span is clamped, but a buggy peer can still
    # ship an oversized payload; stream-read before ``json`` parse.
    sync_blocks_range_response_max_bytes: int = 536_870_912

    # V-4 seal-path missing-data guard, dry-run mode (design
    # docs/design/bridge-state-root-grandfathering.md). Classifies every
    # BRIDGE_LOCK the seal path commits — payload first, envelope fallback —
    # and logs/counts what the real guard WOULD refuse at or above the
    # boundary. Never rejects and never alters the block. Default OFF —
    # enable with BRIDGE_LOCK_GUARD_DRYRUN_ENABLED=true.
    bridge_lock_guard_dryrun_enabled: bool = False
    # Operator-chosen activation boundary (2026-10-08): below it an
    # underivable lock is grandfathered; at/above it is a would-refuse.
    bridge_lock_guard_boundary: int = 30000
    # Follower-side bridge_state_root shadow check (BRIDGE-ROOT-FOLLOW-1):
    # when a P2P/bulk block carries a bridge_state_root, re-derive it from the
    # sealed BRIDGE_LOCK transactions (payload → envelope, never the local
    # CrossChainTransfer table) and log/count mismatches. Compare-only — never
    # rejects, never stores a different root; blocks below the V-4 boundary
    # are skipped. Default OFF — enable with BRIDGE_ROOT_SHADOW_CHECK=true.
    bridge_root_shadow_check: bool = False
    # F1: from this source-chain height the bridge_state_root leaf also commits
    # to the recipient — ``lock:<transfer_id>:<amount>:<target_chain>:<recipient>``
    # instead of ``lock:<transfer_id>:<amount>:<target_chain>``. It changes the
    # root the proposer seals, so every producer must run a build that knows it
    # before the height, and the same value must be set on every host
    # (BRIDGE_LOCK_LEAF_V2_HEIGHT). None (the default) keeps the old leaf for
    # every block. Until it is armed, a confirm whose lock is not on this node
    # cannot prove its recipient and is refused.
    bridge_lock_leaf_v2_height: int | None = None

    # V-3 side-table root shadow (design docs/design/v3-side-table-root-shadow.md).
    # Compare-only soak phase: after each sealed block compute the 13-table
    # committed fingerprint, store it in the node-local shadow_side_root
    # table, log it and bump counters. Never touches the block header, hash,
    # validation or apply. Default OFF for safety — enable with
    # SIDE_ROOT_SHADOW_ENABLED=true.
    side_root_shadow_enabled: bool = False
    # Cost/lifetime knobs while the shadow is soaking: shadow only heights
    # that are multiples of SIDE_ROOT_SHADOW_INTERVAL (default 1 = every
    # block, identical to today), and keep only the newest
    # SIDE_ROOT_SHADOW_RETENTION shadow_side_root rows (default 10_000;
    # <= 0 disables pruning).
    side_root_shadow_interval: int = 1
    side_root_shadow_retention: int = 10_000

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
