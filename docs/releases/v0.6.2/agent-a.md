# v0.6.2 Sync & Gossip Optimization — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create generic sync and gossip utilities — peer capability tracking, state diff computation, message priority queue, delta encoding. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `PeerCapabilityTracker` — track block ranges per peer, select best peer for a range | 🔴 P0 | `aitbc/sync/peer_capability.py` (new), `aitbc/sync/__init__.py` (new) | ✅ |
| A2 | Create `StateDiff` — compute state diff between two account snapshots, encode/decode for transmission | 🔴 P0 | `aitbc/sync/state_diff.py` (new), `aitbc/sync/__init__.py` | ✅ |
| A3 | Create `PriorityMessageQueue` — priority-ordered message queue for gossip (blocks > txs > status) | High | `aitbc/gossip/priority_queue.py` (new), `aitbc/gossip/__init__.py` (new) | ✅ |
| A4 | Unit tests for A1-A3 + verify mypy/ruff/pytest clean | High | `tests/unit/test_peer_capability.py`, `tests/unit/test_state_diff.py`, `tests/unit/test_priority_queue.py` | ✅ |

---

## A1: PeerCapabilityTracker

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

---

## A2: StateDiff

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

---

## A3: PriorityMessageQueue

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

---

## A4: Unit tests + verify clean

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.2 — Sync & Gossip Optimization
**Agent**: Agent A (Shared Core)
