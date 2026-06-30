# v0.6.3 — Multi-Island Node Support Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

## Release Theme

Multi-Island Node Support — Per-Chain Sync Sources, Multi-Hub Subscription, Island-to-Chain Registry.

## Goal

Enable a follower node to sync chains from different hubs on different islands simultaneously. Fix the single-hub/single-chain assumption in the subscription client, enable per-chain sync source mapping, and activate the island manager background tasks.

> **Scope constraint**: This release fixes the sync/subscription/network layer for multi-island awareness. It does NOT add multi-chain-per-island (that's v0.6.4) or bridge functionality (v0.7.0). The gossip topic migration to `transactions.{chain_id}` is already done (v0.6.2).

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) (network compression), [v0.6.2](../v0.6.2/change.log) (sync & gossip optimization), [v0.5.16](../v0.5.16/change.log) (multi-chain preparation — chain_id bug fixes). All complete.

> **Risk**: Medium. Subscription client changes affect runtime behavior (multiple WebSocket connections). Island manager activation enables background tasks. Mitigated by: (1) backward-compatible config (single-hub still works), (2) feature flags for island tasks, (3) per-chain failover isolation.

## Status Baseline — Verified Code Targets

| Component | Location | Current State | v0.6.3 Target |
|-----------|----------|---------------|---------------|
| **SubscriptionClient** | `subscription_client.py` (389 lines) | Single-hub, single-chain. `__init__(hub_url, node_id, chain_id)` at line 23. Only first chain used in main.py:328 | One client per (chain_id, hub_url) pair |
| **Main loop subscription** | `main.py:324-334` | Creates ONE SubscriptionClient with `self._supported_chains()[0]` — only first chain | Create one client per chain, using per-chain hub URL |
| **Island manager setup** | `main.py:294-310` | Creates manager but never calls `start()` — "background tasks disabled" (line 308) | Call `start()`, auto-join islands from config |
| **Island manager tasks** | `island_manager.py:77-87` | `start()` runs `_bridge_request_monitor()` (line 215) and `_island_health_check()` (line 233) | Enable with feature flag + configurable intervals |
| **Sync RPC chain_id** | `sync.py:311,347,537` | ✅ **ALREADY SENDS chain_id** in fetch_blocks_range, bulk_import_from, sync_state_from | No change needed |
| **Gossip topics** | `main.py:149-159` | ✅ **ALREADY chain-specific** — subscribes to `transactions.{chain_id}` + legacy `transactions` | No change needed |
| **TransactionRequest** | `rpc/transactions.py:22,91` | ✅ **ALREADY has chain_id field** — `chain_id: str \| None = None`, uses `get_chain_id(tx_data.chain_id)` | No change needed |
| **Config — sync sources** | `config.py` | ❌ `chain_sync_sources` does NOT exist | Add `chain_sync_sources: str` config field |
| **Config — island registry** | `config.py` | ❌ `island_registry` does NOT exist | Add `island_registry: str` config field |
| **Config — gossip backends** | `config.py:176` | Only `gossip_backend` (singular) exists | Add `gossip_backends: str` for per-chain backends |
| **CLI — chain sync-status** | `cli/aitbc_cli/commands/chain.py` | ❌ Does NOT exist (chain group has `list`, `status`, `info`, `create`, `delete`, `add`, `remove`, `migrate`) | Add `chain sync-status` subcommand to top-level `chain` group |
| **CLI — island health** | `cli/aitbc_cli/commands/node/__init__.py` (island group at line 46-49) | ❌ Does NOT exist (island group has `create`, `join`, `leave`, `list_islands`, `island_info`) | Add `health` subcommand to island group |
| **CLI — island list** | `cli/aitbc_cli/commands/node/island.py:161-174` | EXISTS but is a STUB with hardcoded data (`550e8400-e29b-41d4-a716-446655440000`) | Replace stub with real island manager query; add `list` alias in `node/__init__.py` |

## Already Implemented (verified — no work needed)

1. ✅ **Chain-ID-Aware Sync RPC** — `sync.py` already sends `chain_id` in all RPC calls (fetch_blocks_range line 311, bulk_import_from line 347, sync_state_from line 537)
2. ✅ **Gossip Topic Isolation** — `main.py` already subscribes to `transactions.{chain_id}` (line 155) with legacy `transactions` backward compat (line 150)
3. ✅ **TransactionRequest chain_id** — `rpc/transactions.py` already has `chain_id: str | None = None` (line 22) and uses `get_chain_id(tx_data.chain_id)` (line 91)

## Gossip Topic Migration Window (v0.6.2 → v0.6.3)

The v0.6.2 release already implemented dual-subscribe: `main.py:149-159` subscribes to both `transactions.{chain_id}` (v2) and legacy `transactions` (v1) when `gossip_backward_compat=true`. The v0.6.3 release adds the **migration window management** to phase out v1:

**Migration config** (added in B1 config section):
```bash
GOSSIP_TX_TOPIC_V1=transactions
GOSSIP_TX_TOPIC_V2_TEMPLATE=transactions.{chain_id}
GOSSIP_MIGRATION_DAYS=30
GOSSIP_LOG_V1_WARNINGS=true
```

**v1 warning logging** — in `process_txs()` (main.py:169), when a transaction is received on the legacy v1 topic:
```python
if gossip_log_v1_warnings and source_topic == settings.gossip_tx_topic_v1:
    logger.warning(
        "Received tx on v1 topic from peer %s for chain %s — migrate to v2 topic",
        peer_id, chain_id,
    )
```

**Migration timeline**:
1. **Days 0-30** (dual-subscribe): Both v1 and v2 topics active. v1 messages logged as warnings. All transactions processed correctly.
2. **After 30 days**: Set `GOSSIP_BACKWARD_COMPAT=false`. Drop v1 subscription. Hard-require `chain_id` in topic name. v1 peers rejected at P2P handshake (already implemented in v0.6.2 via `gossip_backward_compat` flag).

**Note**: The v0.6.2 implementation already has the dual-subscribe infrastructure. v0.6.3 only adds: (1) the migration config fields, (2) v1 warning logging in `process_txs()`, (3) documentation of the 30-day window. No new subscription logic needed.

## Architecture: Multi-Hub Subscription

```
┌──────────────────────────────────────────────────────────────────┐
│ main.py — _setup_subscriptions()                                 │
│                                                                  │
│ For each chain_id in supported_chains:                          │
│   1. Resolve hub_url = get_sync_source(chain_id)                │
│      - Check chain_sync_sources mapping                          │
│      - Fall back to default_peer_rpc_url                         │
│   2. If subscription_enabled AND hub_url:                       │
│      - Create SubscriptionClient(hub_url, node_id, chain_id)    │
│      - Start as background task: subscription_{chain_id}        │
│   3. Each client has independent:                                │
│      - WebSocket connection to its hub                           │
│      - Lease management and heartbeat                            │
│      - Failover to pull sync on push failure                     │
│                                                                  │
│ Backward compat: single-hub config → one client (existing path) │
└──────────────────────────────────────────────────────────────────┘
```

## Pre-Coding Integration Test

**This test must be written and pass before any production code is implemented.** It validates the multi-chain sync design using mocks/stubs, ensuring the architecture is sound before investing in implementation.

**Test file**: `apps/blockchain-node/tests/test_multi_island_design.py`

**Test scenario**: Follower node with `supported_chains=ait-hub,ait-island1`, two hub URLs.

```python
class TestMultiChainSyncDesign:
    """Pre-coding integration test — validates design before implementation."""

    def test_sync_both_chains_simultaneously(self):
        """Follower syncs ait-hub from hub-a and ait-island1 from hub-b.
        Verify: both chains sync independently, no cross-contamination."""
        # Setup: SyncSourceResolver with per-chain sources
        resolver = SyncSourceResolver(
            sync_sources="ait-hub:http://hub-a:8006,ait-island1:http://hub-b:8006",
        )
        assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
        assert resolver.get_sync_source("ait-island1") == "http://hub-b:8006"

    def test_no_cross_contamination_in_block_hashes(self):
        """Blocks from hub-a (ait-hub) must not appear in ait-island1's chain."""
        # Mock two hubs returning different blocks
        hub_a_blocks = [{"height": 1, "hash": "aaa", "chain_id": "ait-hub"}]
        hub_b_blocks = [{"height": 1, "hash": "bbb", "chain_id": "ait-island1"}]
        # Verify: chain_id is sent in sync RPC calls
        # Verify: blocks are routed to correct chain's DB session

    def test_chain_id_sent_in_all_sync_rpc_calls(self):
        """Verify chain_id is sent to /rpc/head, /rpc/blocks-range, /rpc/state/snapshot."""
        # Mock HTTP client, capture params
        # Verify: chain_id param present in all sync-related RPC calls

    def test_single_hub_backward_compat(self):
        """Single-hub config (no CHAIN_SYNC_SOURCES) still works."""
        resolver = SyncSourceResolver(
            sync_sources="",
            default_url="http://hub-a:8006",
        )
        # All chains fall back to default
        assert resolver.get_sync_source("ait-hub") == "http://hub-a:8006"
        assert resolver.get_sync_source("ait-island1") == "http://hub-a:8006"
```

**Why write this first**: The test defines the interface contract between `SyncSourceResolver`, `ChainSync`, and the main loop. If the test passes with stubs, the design is validated. Implementation then fills in the real logic.

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/sync/`, `aitbc/network/`, `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/blockchain-node/` (config, main, subscription, island), `cli/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/` utilities. Agent B owns `apps/blockchain-node/` files. Agent B consumes Agent A's utilities.

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.3 — Multi-Island Node Support
