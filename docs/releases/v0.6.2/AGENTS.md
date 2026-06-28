# v0.6.2 — Agent Task Assignment

**Release Theme**: Sync & Gossip Optimization — gossip protocol redesign, parallel sync, delta sync.

**Goal**: Reduce block propagation latency and initial sync time by (1) adding message prioritization and batching to the gossip broker, (2) enabling parallel block fetching from multiple peers, and (3) implementing delta-based state synchronization for fast catch-up.

> **Scope constraint**: This release optimizes the **existing** gossip and sync infrastructure. It does NOT redesign the P2P transport layer (TCP connections, discovery handshake) — that's v0.6.3 (Multi-Island). The gossip topic migration to `transactions.{chain_id}` is also deferred to v0.6.3.

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) (network compression — `GZ:` prefix scheme) and [v0.6.1](../v0.6.1/change.log) (parallel processing — `DependencyGraph`, `ParallelExecutor`, pure state transitions). Both are complete (354+87 tests passing).

> **Risk**: Medium. Gossip changes affect all peers (protocol versioning). Sync changes are behind feature flags. Mitigated by: (1) backward compatibility with v1 peers, (2) feature flags defaulting to off, (3) fallback to sequential sync.

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Component | Location | Current State | v0.6.2 Target |
|-----------|----------|---------------|---------------|
| **Gossip broker** | `gossip/broker.py` (611 lines) | `GossipBroker` singleton, in-memory + Redis backends, compression via `GZ:` prefix | Add message prioritization, batching, protocol versioning |
| **Gossip backend** | `gossip/broker.py:61-227` | `GossipBackend` ABC, `InMemoryGossipBackend`, `BroadcastGossipBackend` | Add batch publish, priority queue |
| **Gossip relay** | `gossip/relay.py` (249 lines) | Standalone Starlette app, not integrated with broker | No change needed (standalone service) |
| **Sync system** | `sync.py` (1,854 lines) | `ChainSync` class, sequential bulk sync, single peer | Add parallel sync, delta sync, peer capability tracking |
| **Bulk sync** | `sync.py:306-410` | `bulk_import_from()` — sequential batch fetching from single peer | Parallel block range requests from multiple peers |
| **State sync** | `sync.py:412-491` | `_sync_account_state()` — full state snapshot from peer | Add delta sync path (only sync changed accounts) |
| **Block fetch** | `sync.py:286-304` | `fetch_blocks_range()` — fetch from single RPC URL | Parallel fetch from multiple peers |
| **Peer tracking** | `network/discovery.py:42-57` | `PeerNode` has `capabilities` field (unused for sync) | Add `PeerCapabilityTracker` for block range tracking |
| **Peer health** | `network/health.py:53-311` | `PeerHealthMonitor` — latency, availability, throughput | Integrate with sync peer selection |
| **Compression** | `network/compression.py` (133 lines) | `GZ:` prefix, `encode_payload`/`decode_payload` | Already done (v0.6.0) — reuse for delta compression |
| **Block header cache** | `aitbc/caching/block_header_cache.py` (107 lines) | LRU cache, `(chain_id, height)` and `(chain_id, hash)` keys | Reuse for delta sync — cache block headers for diff computation |
| **Config** | `config.py:144-178` | Sync settings (batch size, intervals), gossip backend, single peer URL | Add `gossip_protocol_version`, `sync_parallel_enabled`, `sync_delta_enabled` |
| **CLI** | `cli/aitbc_cli/commands/sync.py` (71 lines) | Only `sync bulk` command | Add `sync status` command |
| **Main loop** | `main.py:141-250` | Gossip subscribers for `transactions` and `blocks.{chain_id}` topics | No change needed (gossip topics are v0.6.3 scope) |
| **Tests** | `test_gossip_network.py` (544 lines), `test_sync.py` (529 lines) | 24 gossip tests, 30 sync tests | Add parallel sync tests, delta sync tests, gossip priority tests |

### Architecture: Parallel Sync Approach

```
┌──────────────────────────────────────────────────────────────────┐
│ bulk_import_from (sync.py)                                       │
│                                                                  │
│ 1. Fetch local + remote head                                    │
│ 2. Calculate gap (remote_height - local_height)                 │
│ 3. If sync_parallel_enabled AND multiple peers available:       │
│    a. Divide gap into sub-ranges (one per peer)                 │
│    b. Request each sub-range in parallel (asyncio.gather)       │
│    c. Merge results deterministically (by block height)         │
│    d. Import merged block list                                  │
│ 4. Else: sequential batch fetch (existing path)                 │
│ 5. If sync_delta_enabled AND gap < delta_threshold:             │
│    a. Request state delta from peer (changed accounts only)     │
│    b. Verify delta against block headers + state roots          │
│    c. Apply delta to local state                                │
│    d. Verify resulting state root                               │
│ 6. Else: full state sync (existing path)                        │
│                                                                  │
│ Feature flags: sync_parallel_enabled=false, sync_delta_enabled=false │
└──────────────────────────────────────────────────────────────────┘
```

**Why this works**:
- **Parallel sync**: Divides the block range into sub-ranges, each fetched from a different peer. Results are merged by block height (deterministic). If a peer fails, re-request from another peer.
- **Delta sync**: Instead of fetching all accounts, only fetch accounts that changed between `local_height` and `remote_height`. The peer computes the diff and sends only changed accounts. Falls back to full sync if delta > 50% of full state.
- **Feature flags**: Both paths default to off. Sequential sync remains the default.

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/sync/`, `aitbc/gossip/`, `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/blockchain-node/src/aitbc_chain/` (gossip, sync, config), `cli/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/sync/` and `aitbc/gossip/` modules. Agent B owns `apps/blockchain-node/` files. Agent B consumes Agent A's utilities — see Coordination Protocol.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create generic sync and gossip utilities — peer capability tracking, state diff computation, message priority queue, delta encoding. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `PeerCapabilityTracker` — track block ranges per peer, select best peer for a range | 🔴 P0 | `aitbc/sync/peer_capability.py` (new), `aitbc/sync/__init__.py` (new) | ⬜ |
| A2 | Create `StateDiff` — compute state diff between two account snapshots, encode/decode for transmission | 🔴 P0 | `aitbc/sync/state_diff.py` (new), `aitbc/sync/__init__.py` | ⬜ |
| A3 | Create `PriorityMessageQueue` — priority-ordered message queue for gossip (blocks > txs > status) | High | `aitbc/gossip/priority_queue.py` (new), `aitbc/gossip/__init__.py` (new) | ⬜ |
| A4 | Unit tests for A1-A3 + verify mypy/ruff/pytest clean | High | `tests/unit/test_peer_capability.py`, `tests/unit/test_state_diff.py`, `tests/unit/test_priority_queue.py` | ⬜ |

### Agent A — Detailed Instructions

#### A1: PeerCapabilityTracker

Create `aitbc/sync/peer_capability.py`:

```python
from dataclasses import dataclass, field

@dataclass
class PeerCapability:
    """Tracks what blocks a peer has available for sync."""
    peer_id: str
    rpc_url: str
    block_range: tuple[int, int]  # (min_height, max_height)
    has_state: bool = False  # can provide state snapshots/deltas
    last_updated: float = 0.0  # timestamp
    latency_ms: float = 0.0  # measured latency
    reputation: float = 1.0  # 0.0-1.0, decreases on failures

class PeerCapabilityTracker:
    """Tracks peer capabilities for parallel sync peer selection.

    Maintains a registry of peers and their block ranges. When a sync
    is needed, divides the missing range into sub-ranges and assigns
    each to the best available peer (lowest latency, highest reputation).
    """

    def __init__(self) -> None: ...

    def register_peer(self, capability: PeerCapability) -> None:
        """Register or update a peer's capabilities."""
        ...

    def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from the tracker."""
        ...

    def get_peer(self, peer_id: str) -> PeerCapability | None:
        """Get a peer's capability by ID."""
        ...

    def get_all_peers(self) -> list[PeerCapability]:
        """Get all registered peers, sorted by reputation (descending)."""
        ...

    def select_peers_for_range(
        self, start_height: int, end_height: int, max_peers: int = 4
    ) -> list[tuple[str, tuple[int, int]]]:
        """Select peers to fetch a block range in parallel.

        Divides [start_height, end_height] into sub-ranges, one per peer.
        Returns list of (peer_id, sub_range) tuples.

        Selection criteria:
        1. Peer must have the block range (block_range covers sub-range)
        2. Sort by (reputation * 1000 - latency_ms) descending
        3. Assign sub-ranges to top N peers

        If fewer peers than sub-ranges, some peers get larger ranges.
        If no peers have the range, return empty list (caller falls back to sequential).
        """
        ...

    def record_success(self, peer_id: str, blocks_fetched: int) -> None:
        """Record a successful sync from this peer (increases reputation)."""
        ...

    def record_failure(self, peer_id: str, reason: str = "") -> None:
        """Record a failed sync from this peer (decreases reputation)."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Return stats: total_peers, avg_reputation, avg_latency."""
        ...
```

**Key design**:
- `select_peers_for_range` divides the range evenly across available peers
- Reputation starts at 1.0, decreases by 0.1 on failure (min 0.0), increases by 0.05 on success (max 1.0)
- Peers with reputation < 0.3 are excluded from selection
- Thread-safe (use `threading.Lock` for registry mutations)

Export from `aitbc/sync/__init__.py` as `PeerCapability`, `PeerCapabilityTracker`.

#### A2: StateDiff

Create `aitbc/sync/state_diff.py`:

```python
from dataclasses import dataclass

@dataclass
class AccountChange:
    """A single account state change in a diff."""
    address: str
    old_balance: int
    new_balance: int
    old_nonce: int
    new_nonce: int
    is_new: bool = False  # account didn't exist before
    is_deleted: bool = False  # account was deleted

@dataclass
class StateDiff:
    """State diff between two block heights.

    Contains only the accounts that changed. Can be encoded for
    transmission and applied to local state.
    """
    from_height: int
    to_height: int
    changes: list[AccountChange]
    from_state_root: str
    to_state_root: str

    def size_bytes(self) -> int:
        """Estimated serialized size in bytes."""
        ...

    def is_too_large(self, full_state_size: int, threshold: float = 0.5) -> bool:
        """Check if delta is too large (should fall back to full sync).

        Returns True if diff size > threshold * full_state_size.
        """
        ...

def compute_state_diff(
    old_accounts: dict[str, tuple[int, int]],  # {address: (balance, nonce)}
    new_accounts: dict[str, tuple[int, int]],
    from_height: int,
    to_height: int,
    from_state_root: str,
    to_state_root: str,
) -> StateDiff:
    """Compute the diff between two account snapshots.

    Pure function — takes two snapshots, returns a StateDiff.
    Detects: new accounts, deleted accounts, balance changes, nonce changes.
    """
    ...

def encode_state_diff(diff: StateDiff) -> bytes:
    """Encode a StateDiff for transmission (compressed).

    Uses JSON serialization + gzip compression (reuse aitbc.network.compression).
    """
    ...

def decode_state_diff(data: bytes) -> StateDiff:
    """Decode a StateDiff from compressed bytes."""
    ...

def apply_state_diff(
    diff: StateDiff,
    account_map: dict[str, Any],  # Account-like objects with balance/nonce
) -> list[str]:
    """Apply a StateDiff to an account_map.

    Mutates account_map in place. Creates new accounts, updates existing,
    handles deletions. Returns list of changed addresses.
    """
    ...
```

**Key design**:
- `compute_state_diff` is pure — takes two snapshots, returns diff
- `encode_state_diff` / `decode_state_diff` use `aitbc.network.compress_json` / `decompress_json`
- `apply_state_diff` mutates account_map (similar to `apply_delta_to_map` in v0.6.1)
- `is_too_large` checks if delta > 50% of full state (configurable threshold)

Export from `aitbc/sync/__init__.py` as `AccountChange`, `StateDiff`, `compute_state_diff`, `encode_state_diff`, `decode_state_diff`, `apply_state_diff`.

#### A3: PriorityMessageQueue

Create `aitbc/gossip/priority_queue.py`:

```python
import heapq
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class PrioritizedMessage:
    """A gossip message with a priority level.

    Lower priority value = higher priority (sent first).
    """
    priority: int  # 1=highest (blocks), 5=lowest (discovery)
    sequence: int  # monotonic counter for FIFO within same priority
    topic: str = field(compare=False)
    message: Any = field(compare=False)

class PriorityMessageQueue:
    """Priority queue for gossip messages.

    Messages are ordered by priority (blocks first, then transactions,
    then status, then discovery). Within the same priority, messages
    are FIFO (by sequence number).

    Thread-safe for concurrent producers and a single consumer.
    """

    # Priority levels
    PRIORITY_BLOCK = 1
    PRIORITY_BLOCK_HEADER = 2
    PRIORITY_TRANSACTION = 3
    PRIORITY_STATUS = 4
    PRIORITY_DISCOVERY = 5

    def __init__(self, max_size: int = 10000) -> None: ...

    def put(self, topic: str, message: Any, priority: int = PRIORITY_TRANSACTION) -> None:
        """Add a message to the queue with given priority."""
        ...

    def get(self, timeout: float | None = None) -> PrioritizedMessage | None:
        """Get the highest-priority message. Returns None if empty/timeout."""
        ...

    def get_batch(self, max_count: int = 100) -> list[PrioritizedMessage]:
        """Get up to max_count messages, ordered by priority then sequence.
        Used for batch sending."""
        ...

    def qsize(self) -> int:
        """Current queue size."""
        ...

    def clear(self) -> None:
        """Clear all messages."""
        ...
```

**Key design**:
- Uses `heapq` for priority ordering
- `sequence` counter ensures FIFO within same priority
- Thread-safe (use `threading.Lock` + `threading.Condition` for blocking get)
- `get_batch` enables batch sending (multiple messages in one gossip frame)

Export from `aitbc/gossip/__init__.py` as `PrioritizedMessage`, `PriorityMessageQueue`.

#### A4: Unit tests + verify clean

**`tests/unit/test_peer_capability.py`**:
- `test_register_and_get_peer` — register, get, remove
- `test_select_peers_for_range_even_division` — 4 peers, 100 blocks → 4 sub-ranges of 25
- `test_select_peers_fewer_peers_than_ranges` — 2 peers, 100 blocks → 2 sub-ranges of 50
- `test_select_peers_no_peers_with_range` — no peers have the blocks → empty list
- `test_select_peers_filters_low_reputation` — peer with reputation < 0.3 excluded
- `test_select_peers_sorts_by_reputation_and_latency` — best peer gets first pick
- `test_record_success_increases_reputation` — reputation goes up
- `test_record_failure_decreases_reputation` — reputation goes down
- `test_get_stats` — verify stats output
- `test_thread_safety` — concurrent register/select doesn't crash

**`tests/unit/test_state_diff.py`**:
- `test_compute_state_diff_no_changes` — identical snapshots → empty diff
- `test_compute_state_diff_new_account` — account in new but not old
- `test_compute_state_diff_deleted_account` — account in old but not new
- `test_compute_state_diff_balance_change` — balance changed
- `test_compute_state_diff_nonce_change` — nonce changed
- `test_encode_decode_roundtrip` — encode then decode produces same diff
- `test_apply_state_diff_creates_new` — apply diff with new account
- `test_apply_state_diff_updates_existing` — apply diff with balance change
- `test_is_too_large_false` — small diff, large state → False
- `test_is_too_large_true` — diff > 50% of state → True

**`tests/unit/test_priority_queue.py`**:
- `test_priority_ordering` — block messages come before transaction messages
- `test_fifo_within_same_priority` — same priority, FIFO by sequence
- `test_get_batch` — get multiple messages at once
- `test_empty_queue_get_returns_none` — get on empty queue
- `test_qsize` — verify size tracking
- `test_clear` — clear all messages
- `test_thread_safety` — concurrent put/get doesn't crash

**A4 verification**:
- `mypy aitbc/` — 0 errors
- `ruff check aitbc/` — 0 errors
- `pytest tests/unit -q` — all pass

---

## Agent B — Apps & Infrastructure

**Scope**: Wire up parallel sync and delta sync in `sync.py`, add gossip prioritization to `broker.py`, add config settings, add CLI `sync status` command, and write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add gossip protocol config — `gossip_protocol_version`, `sync_parallel_enabled`, `sync_delta_enabled` | High | `config.py` | ⬜ |
| B2 | Wire up `PriorityMessageQueue` in `gossip/broker.py` — prioritize block messages over txs | High | `gossip/broker.py` | ⬜ |
| B3 | Add message batching to `gossip/broker.py` — batch small messages into single frame | Medium | `gossip/broker.py` | ⬜ |
| B4 | Wire up `PeerCapabilityTracker` in `sync.py` — track peer block ranges, register on peer connect | 🔴 P0 | `sync.py` | ⬜ |
| B5 | Wire up parallel sync in `sync.py` `bulk_import_from()` — divide range, fetch in parallel, merge | 🔴 P0 | `sync.py` | ⬜ |
| B6 | Wire up delta sync in `sync.py` — `delta_sync_from()` method using `StateDiff` | High | `sync.py` | ⬜ |
| B7 | Add `sync status` CLI command — show current block, peer count, sync progress | Medium | `cli/aitbc_cli/commands/sync.py` | ⬜ |
| B8 | Integration tests — parallel sync, delta sync, gossip priority, CLI | 🔴 P0 | `apps/blockchain-node/tests/test_sync_optimization.py` (new), `apps/blockchain-node/tests/test_gossip_priority.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Add gossip + sync config

Add to `config.py` `ChainSettings` class (following existing pattern):

```python
# Gossip protocol (v0.6.2)
gossip_protocol_version: int = 2  # Protocol version (1=legacy, 2=optimized)
gossip_backward_compat: bool = True  # Accept v1 peers with deprecation
gossip_legacy_peer_timeout: int = 3600  # Seconds before disconnecting v1 peers
gossip_message_batch_size: int = 10  # Max messages per batched gossip frame
gossip_priority_enabled: bool = False  # Enable message prioritization (default off)

# Parallel sync (v0.6.2)
sync_parallel_enabled: bool = False  # Feature flag — default off for safety
sync_parallel_max_peers: int = 4  # Max peers for parallel block fetching
sync_parallel_timeout: float = 30.0  # Timeout per peer request (seconds)

# Delta sync (v0.6.2)
sync_delta_enabled: bool = False  # Feature flag — default off for safety
sync_delta_threshold: float = 0.5  # Fall back to full sync if delta > 50% of state
sync_delta_max_blocks: int = 100  # Max blocks for delta sync (use full sync above this)
```

**Verify**: Config loads correctly with defaults. Env vars bind: `GOSSIP_PROTOCOL_VERSION`, `SYNC_PARALLEL_ENABLED`, `SYNC_DELTA_ENABLED`, etc.

#### B2: Wire up PriorityMessageQueue in broker.py

Modify `gossip/broker.py`:

1. Import `PriorityMessageQueue` from `aitbc.gossip`
2. Add a `PriorityMessageQueue` instance to `GossipBroker` (when `gossip_priority_enabled=True`)
3. Modify `GossipBroker.publish()` to route through priority queue when enabled:
   - Block topics (`blocks.*`) → `PRIORITY_BLOCK`
   - Transaction topics (`transactions*`) → `PRIORITY_TRANSACTION`
   - Status topics → `PRIORITY_STATUS`
4. Add a background task that drains the queue and publishes to the backend
5. Keep the existing direct-publish path when `gossip_priority_enabled=False` (default)

**Feature flag**: `settings.gossip_priority_enabled` (default `False`).

**⚠️ Critical**: The priority queue must not change message ordering within the same priority level. Blocks must still arrive in height order.

#### B3: Add message batching to broker.py

Modify `gossip/broker.py`:

1. When `gossip_message_batch_size > 1`, batch multiple small messages into a single gossip frame
2. Add `_encode_batch(messages: list[dict]) -> str` and `_decode_batch(data: str) -> list[dict]`
3. Batch format: JSON array of messages, compressed with `GZ:` prefix
4. Modify `BroadcastGossipBackend.publish()` to accept a list of messages for batching
5. Modify `BroadcastGossipBackend.subscribe()` to handle batched messages (decode array)
6. Backward compatibility: if a message doesn't start with `[` after decompression, treat as single message

**Verify**: Existing gossip tests pass. Add test for batch encode/decode roundtrip.

#### B4: Wire up PeerCapabilityTracker in sync.py

Modify `sync.py`:

1. Import `PeerCapabilityTracker`, `PeerCapability` from `aitbc.sync`
2. Add a `PeerCapabilityTracker` instance to `ChainSync.__init__`
3. Add `register_sync_peer(peer_id, rpc_url, block_range, has_state)` method
4. Add `update_peer_capability(peer_id, block_range)` method (called after fetching remote head)
5. In `bulk_import_from()`, after fetching remote head, register the peer's capability:
   ```python
   self._peer_tracker.register_peer(PeerCapability(
       peer_id=source_url,
       rpc_url=source_url,
       block_range=(0, remote_head["height"]),
       has_state=True,
   ))
   ```
6. Call `record_success`/`record_failure` after each batch fetch

**Note**: For now, only one peer is registered (the `source_url`). Multi-peer support comes in v0.6.3 when island managers provide peer lists. The tracker is ready for multi-peer but works with single peer too.

#### B5: Wire up parallel sync in bulk_import_from()

Modify `sync.py` `bulk_import_from()` (lines 306-410):

1. Add feature flag check: `if settings.sync_parallel_enabled and self._peer_tracker.get_all_peers() > 1:`
2. For the parallel path:
   a. Get the gap: `gap_start = local_head + 1`, `gap_end = remote_head`
   b. Call `self._peer_tracker.select_peers_for_range(gap_start, gap_end, max_peers=settings.sync_parallel_max_peers)`
   c. If no peers selected, fall back to sequential
   d. For each `(peer_id, sub_range)`, call `fetch_blocks_range(peer_id, sub_range[0], sub_range[1])` in parallel using `asyncio.gather()`
   e. Merge results: concatenate all block lists, sort by height, deduplicate by hash
   f. Import merged block list (existing import logic)
   g. Call `record_success` for successful peers, `record_failure` for failed ones
3. Keep the sequential path as fallback (when `sync_parallel_enabled=False` or only 1 peer)

**⚠️ Critical**: The merged block list must be identical regardless of which peer provided which blocks. Blocks are ordered by height. If two peers provide different blocks for the same height, use the block with the hash that matches the majority (conflict resolution). If no majority, flag all conflicting peers and fall back to sequential.

**Note**: `fetch_blocks_range` currently takes a URL string. It needs to be refactored to accept a peer_id or URL. For now, peer_id IS the URL (since we only have one peer in v0.6.2).

#### B6: Wire up delta sync

Add `delta_sync_from()` method to `ChainSync`:

```python
async def delta_sync_from(self, source_url: str, from_height: int, to_height: int) -> dict:
    """Sync state delta from a peer (only changed accounts).

    1. Request state delta from peer: POST /sync/delta {from_height, to_height}
    2. Receive StateDiff (encoded + compressed)
    3. Decode StateDiff
    4. Check if delta is too large (fallback to full sync)
    5. Apply delta to local state
    6. Verify resulting state root matches expected
    7. Return sync statistics
    """
```

Also add the RPC endpoint for serving delta requests (in `rpc/sync.py` or `rpc/router.py`):
- `POST /sync/delta` — accepts `{from_height, to_height}`, returns encoded `StateDiff`
- Computes diff by comparing account state at `from_height` vs `to_height`
- Uses `compute_state_diff` from `aitbc.sync`

**Feature flag**: `settings.sync_delta_enabled` (default `False`).

**Fallback**: If `to_height - from_height > settings.sync_delta_max_blocks` or delta is too large, fall back to full state sync (`_sync_account_state`).

**Note**: The RPC endpoint for serving deltas requires knowing account state at a historical height. For now, this can be approximated by replaying transactions from `from_height` to `to_height` and tracking which accounts changed. A full historical state snapshot is not available.

#### B7: Add `sync status` CLI command

Add to `cli/aitbc_cli/commands/sync.py`:

```python
@sync.command()
@click.option("--chain-id", default=None, help="Chain ID to check")
def status(chain_id):
    """Show synchronization status (current block, peer count, sync progress)."""
    # Query local node:
    # - GET /chain/{chain_id}/head → current block height
    # - GET /sync/peers → registered sync peers and capabilities
    # - GET /metrics/sync → sync metrics (blocks/sec, last sync time, mode)
    # Display in a table format
```

**Implementation**:
- Use `SharedHttpClient` (from v0.6.0) to query the local node's RPC
- Display: chain ID, local height, peer count, peer block ranges, sync mode, last sync time, blocks/sec
- If no node running, show error message

#### B8: Integration tests

Create `apps/blockchain-node/tests/test_sync_optimization.py`:

```python
class TestParallelSync:
    """Test parallel block fetching from multiple peers."""
    def test_parallel_sync_divides_range_evenly(self): ...
    def test_parallel_sync_merges_results_by_height(self): ...
    def test_parallel_sync_handles_peer_failure(self): ...
    def test_parallel_sync_falls_back_to_sequential(self): ...
    def test_parallel_sync_conflict_resolution(self): ...

class TestDeltaSync:
    """Test delta-based state synchronization."""
    def test_delta_sync_applies_only_changed_accounts(self): ...
    def test_delta_sync_falls_back_when_too_large(self): ...
    def test_delta_sync_falls_back_when_too_many_blocks(self): ...
    def test_delta_sync_verifies_state_root(self): ...
    def test_delta_sync_rollback_on_mismatch(self): ...

class TestPeerCapabilityTracker:
    """Test peer capability tracking in ChainSync."""
    def test_register_peer_updates_tracker(self): ...
    def test_record_success_increases_reputation(self): ...
    def test_record_failure_decreases_reputation(self): ...
```

Create `apps/blockchain-node/tests/test_gossip_priority.py`:

```python
class TestGossipPriority:
    """Test gossip message prioritization."""
    def test_block_messages_have_higher_priority(self): ...
    def test_priority_queue_preserves_fifo_within_priority(self): ...
    def test_priority_disabled_uses_direct_publish(self): ...
    def test_message_batching_encode_decode(self): ...
    def test_batch_backward_compat_single_message(self): ...
```

**Verify**: All tests pass. Existing 354+ tests still pass.

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/sync/peer_capability.py` | Agent A | A1: new file |
| `aitbc/sync/state_diff.py` | Agent A | A2: new file |
| `aitbc/sync/__init__.py` | Agent A | A1, A2: exports |
| `aitbc/gossip/priority_queue.py` | Agent A | A3: new file |
| `aitbc/gossip/__init__.py` | Agent A | A3: exports |
| `tests/unit/test_peer_capability.py` | Agent A | A4 |
| `tests/unit/test_state_diff.py` | Agent A | A4 |
| `tests/unit/test_priority_queue.py` | Agent A | A4 |
| `apps/blockchain-node/src/aitbc_chain/config.py` | Agent B | B1: config additions |
| `apps/blockchain-node/src/aitbc_chain/gossip/broker.py` | Agent B | B2, B3: priority queue + batching |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | Agent B | B4, B5, B6: peer tracker + parallel sync + delta sync |
| `cli/aitbc_cli/commands/sync.py` | Agent B | B7: sync status command |
| `apps/blockchain-node/tests/test_sync_optimization.py` | Agent B | B8 |
| `apps/blockchain-node/tests/test_gossip_priority.py` | Agent B | B8 |

### Dependency Graph

```
Phase 1 (Agent A — parallel, no dependencies):
  A1 PeerCapabilityTracker
  A2 StateDiff
  A3 PriorityMessageQueue
  A4 unit tests + verify clean

Phase 2 (Agent B — after A1-A3 are merged):
  B1 gossip + sync config              (independent of A)
  B7 sync status CLI                   (independent of A)

Phase 3 (Agent B — after A1-A3 + B1):
  B2 wire up PriorityMessageQueue      (depends on A3, B1)
  B3 message batching                  (depends on B1, touches broker.py — coordinate with B2)
  B4 wire up PeerCapabilityTracker     (depends on A1, B1)
  B5 parallel sync                     (depends on A1, B1, B4)
  B6 delta sync                        (depends on A2, B1)

Phase 4 (Agent B — after B2-B6):
  B8 integration tests                 (depends on B2, B3, B4, B5, B6)
```

**B1, B7 can start immediately** (no Agent A dependency). B2-B6 depend on A1-A3. B8 depends on B2-B6.

### Execution Order

1. **Agent A** starts immediately on A1-A4 (all parallel, no dependencies)
2. **Agent B** starts B1 (config) and B7 (CLI) in parallel with Agent A
3. After A1-A3 are merged, **Agent B** starts B2-B6 (can be parallelized across files)
4. After B2-B6 are done, **Agent B** does B8 (integration tests)
5. Final verification: full test suite + mypy + ruff

---

## Success Criteria

- ✅ Gossip message prioritization operational (feature flag, default off)
- ✅ Message batching reduces gossip overhead
- ✅ Parallel sync reduces initial sync time (feature flag, default off)
- ✅ Delta sync enables fast catch-up (feature flag, default off)
- ✅ `sync status` CLI command works
- ✅ All existing tests pass (354 baseline from v0.6.1)
- ✅ New tests pass (parallel sync, delta sync, gossip priority)
- ✅ mypy + ruff clean
- ✅ No consensus failures (sync changes are behind feature flags)
