# v0.6.2 Sync & Gossip Optimization — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Wire up parallel sync and delta sync in `sync.py`, add gossip prioritization to `broker.py`, add config settings, add CLI `sync status` command, and write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add gossip protocol config — `gossip_protocol_version`, `sync_parallel_enabled`, `sync_delta_enabled` | High | `config.py` | ✅ |
| B2 | Wire up `PriorityMessageQueue` in `gossip/broker.py` — prioritize block messages over txs | High | `gossip/broker.py` | ✅ |
| B3 | Add message batching to `gossip/broker.py` — batch small messages into single frame | Medium | `gossip/broker.py` | ✅ |
| B4 | Wire up `PeerCapabilityTracker` in `sync.py` — track peer block ranges, register on peer connect | 🔴 P0 | `sync.py` | ✅ |
| B5 | Wire up parallel sync in `sync.py` `bulk_import_from()` — divide range, fetch in parallel, merge | 🔴 P0 | `sync.py` | ✅ |
| B6 | Wire up delta sync in `sync.py` — `delta_sync_from()` method using `StateDiff` | High | `sync.py` | ✅ |
| B7 | Add `sync status` CLI command — show current block, peer count, sync progress | Medium | `cli/aitbc_cli/commands/sync.py` | ✅ |
| B8 | Integration tests — parallel sync, delta sync, gossip priority, CLI | 🔴 P0 | `apps/blockchain-node/tests/test_sync_optimization.py` (new), `apps/blockchain-node/tests/test_gossip_priority.py` (new) | ✅ |

---

## B1: Add gossip + sync config

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

---

## B2: Wire up PriorityMessageQueue

In `gossip/broker.py`:
- Import `PriorityMessageQueue` from `aitbc.gossip.priority_queue`
- Add `priority_queue: PriorityMessageQueue` field to `GossipBroker`
- Initialize in `__init__` if `config.gossip_priority_enabled=True`
- In `publish()`, route messages through priority queue instead of direct backend publish
- Add `get_batch()` method to fetch batch of messages for sending

---

## B3: Add message batching

In `gossip/broker.py`:
- Add `batch_publish()` method that calls `priority_queue.get_batch()`
- Batch up to `config.gossip_message_batch_size` messages
- Serialize batch as single gossip frame (JSON array with compression)
- Update `GossipBackend` ABC to support batch publish

---

## B4: Wire up PeerCapabilityTracker

In `sync.py`:
- Import `PeerCapabilityTracker` from `aitbc.sync.peer_capability`
- Add `peer_tracker: PeerCapabilityTracker` field to `ChainSync`
- Initialize in `__init__`
- In peer discovery callback (when new peer connects), register peer with their block range
- In peer disconnect callback, remove peer from tracker
- Add `update_peer_capabilities()` method to refresh peer info

---

## B5: Wire up parallel sync

In `sync.py` `bulk_import_from()`:
- After calculating gap, check `config.sync_parallel_enabled`
- If enabled, call `peer_tracker.select_peers_for_range()` to get peer assignments
- Use `asyncio.gather()` to fetch sub-ranges in parallel
- Merge results by block height (deterministic sort)
- If a peer fails, re-request from another peer or fall back to sequential
- Add timeout per peer request (`config.sync_parallel_timeout`)

---

## B6: Wire up delta sync

In `sync.py`:
- Add `delta_sync_from()` method
- Import `StateDiff`, `compute_state_diff`, `encode_state_diff`, `decode_state_diff`, `apply_state_diff` from `aitbc.sync.state_diff`
- Check `config.sync_delta_enabled` and gap size (< `sync_delta_max_blocks`)
- Request state delta from peer via new RPC endpoint (see B6 extension)
- Decode delta, verify against block headers + state roots
- Apply delta to local state
- Verify resulting state root matches expected
- Fall back to full sync if delta is too large or verification fails

---

## B7: Add sync status CLI command

In `cli/aitbc_cli/commands/sync.py`:
- Add `status` subcommand to `sync` command group
- Display: current block height, peer count, sync progress, parallel/delta enabled status
- Call RPC endpoint `/sync/status` to get node sync state

---

## B8: Integration tests

Create `apps/blockchain-node/tests/test_sync_optimization.py`:
- `test_parallel_sync_with_multiple_peers` — 4 peers, 100 blocks → parallel fetch
- `test_parallel_sync_fallback_to_sequential` — no peers available → sequential
- `test_parallel_sync_peer_failure_retry` — one peer fails → retry with another
- `test_delta_sync_small_gap` — 50 blocks gap → delta sync
- `test_delta_sync_fallback_to_full` — delta too large → full sync
- `test_delta_sync_verification` — verify state root after applying delta
- `test_peer_capability_tracker_integration` — register peers, select for range

Create `apps/blockchain-node/tests/test_gossip_priority.py`:
- `test_gossip_priority_queue_integration` — block messages prioritized over txs
- `test_gossip_batch_publish` — multiple messages in single frame
- `test_gossip_backward_compat_v1_peer` — accept v1 peer with deprecation warning

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.2 — Sync & Gossip Optimization
**Agent**: Agent B (Apps & Infrastructure)
