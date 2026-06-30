# v0.6.2 Sync & Gossip Optimization — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Sync & Gossip Optimization — gossip protocol redesign, parallel sync, delta sync.

**Goal**: Reduce block propagation latency and initial sync time by (1) adding message prioritization and batching to the gossip broker, (2) enabling parallel block fetching from multiple peers, and (3) implementing delta-based state synchronization for fast catch-up.

> **Scope constraint**: This release optimizes the **existing** gossip and sync infrastructure. It does NOT redesign the P2P transport layer (TCP connections, discovery handshake) — that's v0.6.3 (Multi-Island). The gossip topic migration to `transactions.{chain_id}` is also deferred to v0.6.3.

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) (network compression — `GZ:` prefix scheme) and [v0.6.1](../v0.6.1/change.log) (parallel processing — `DependencyGraph`, `ParallelExecutor`, pure state transitions). Both are complete (354+87 tests passing).

> **Risk**: Medium. Gossip changes affect all peers (protocol versioning). Sync changes are behind feature flags. Mitigated by: (1) backward compatibility with v1 peers, (2) feature flags defaulting to off, (3) fallback to sequential sync.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (peer capability tracking, state diff computation, message priority queue, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (gossip prioritization, parallel sync, delta sync, config, CLI, integration tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation)
- [Architecture: Parallel Sync Approach](#architecture-parallel-sync-approach)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [PeerCapabilityTracker](./agent-a.md#a1-peercapabilitytracker)
- [StateDiff](./agent-a.md#a2-statediff)
- [PriorityMessageQueue](./agent-a.md#a3-prioritymessagequeue)
- [Unit tests + verify clean](./agent-a.md#a4-unit-tests--verify-clean)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Add gossip + sync config](./agent-b.md#b1-add-gossip--sync-config)
- [Wire up PriorityMessageQueue](./agent-b.md#b2-wire-up-prioritymessagequeue-in-gossipbrokerpy)
- [Add message batching](./agent-b.md#b3-add-message-batching-to-gossipbrokerpy)
- [Wire up PeerCapabilityTracker](./agent-b.md#b4-wire-up-peercapabilitytracker-in-syncpy)
- [Wire up parallel sync](./agent-b.md#b5-wire-up-parallel-sync-in-syncpy-bulk_import_from)
- [Wire up delta sync](./agent-b.md#b6-wire-up-delta-sync-in-syncpy)
- [Add sync status CLI command](./agent-b.md#b7-add-sync-status-cli-command)
- [Integration tests](./agent-b.md#b8-integration-tests)

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

---

## Architecture: Parallel Sync Approach

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.2 — Sync & Gossip Optimization
