# v0.6.3 — Agent Task Assignment

**Release Theme**: Multi-Island Node Support — Per-Chain Sync Sources, Multi-Hub Subscription, Island-to-Chain Registry.

**Goal**: Enable a follower node to sync chains from different hubs on different islands simultaneously. Fix the single-hub/single-chain assumption in the subscription client, enable per-chain sync source mapping, and activate the island manager background tasks.

> **Scope constraint**: This release fixes the sync/subscription/network layer for multi-island awareness. It does NOT add multi-chain-per-island (that's v0.6.4) or bridge functionality (v0.7.0). The gossip topic migration to `transactions.{chain_id}` is already done (v0.6.2).

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) (network compression), [v0.6.2](../v0.6.2/change.log) (sync & gossip optimization), [v0.5.16](../v0.5.16/change.log) (multi-chain preparation — chain_id bug fixes). All complete.

> **Risk**: Medium. Subscription client changes affect runtime behavior (multiple WebSocket connections). Island manager activation enables background tasks. Mitigated by: (1) backward-compatible config (single-hub still works), (2) feature flags for island tasks, (3) per-chain failover isolation.

---

## Status Baseline — Verified Code Targets (from subagent investigation)

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

### Already Implemented (verified — no work needed)

1. ✅ **Chain-ID-Aware Sync RPC** — `sync.py` already sends `chain_id` in all RPC calls (fetch_blocks_range line 311, bulk_import_from line 347, sync_state_from line 537)
2. ✅ **Gossip Topic Isolation** — `main.py` already subscribes to `transactions.{chain_id}` (line 155) with legacy `transactions` backward compat (line 150)
3. ✅ **TransactionRequest chain_id** — `rpc/transactions.py` already has `chain_id: str | None = None` (line 22) and uses `get_chain_id(tx_data.chain_id)` (line 91)

### Gossip Topic Migration Window (v0.6.2 → v0.6.3)

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

### Architecture: Multi-Hub Subscription

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

### Pre-Coding Integration Test (write first, validate design before implementation)

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

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/sync/`, `aitbc/network/`, `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/blockchain-node/` (config, main, subscription, island), `cli/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/` utilities. Agent B owns `apps/blockchain-node/` files. Agent B consumes Agent A's utilities.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create generic sync source resolution and island registry parsing utilities. These are blockchain-agnostic and reusable.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `SyncSourceResolver` — parse chain_sync_sources, resolve hub URL per chain | 🔴 P0 | `aitbc/sync/source_resolver.py` (new), `aitbc/sync/__init__.py` (update) | ✅ |
| A2 | Create `IslandRegistry` — parse island_registry config, map island_id → chain_id → hub_url | High | `aitbc/network/island_registry.py` (new), `aitbc/network/__init__.py` (update) | ✅ |
| A3 | Unit tests for A1-A4 + verify mypy/ruff/pytest clean | High | `tests/unit/test_sync_source_resolver.py`, `tests/unit/test_island_registry.py`, `tests/unit/test_subscription_manager.py` | ✅ |
| A4 | Create `SubscriptionManager` — generic multi-hub subscription tracking, per-(chain_id, hub_url) lifecycle | 🔴 P0 | `aitbc/network/subscription_manager.py` (new), `aitbc/network/__init__.py` (update) | ✅ |

### Agent A — Detailed Instructions

#### A1: SyncSourceResolver

Create `aitbc/sync/source_resolver.py`:

```python
from __future__ import annotations


class SyncSourceResolver:
    """Resolves sync source URLs per chain_id.

    Parses the CHAIN_SYNC_SOURCES config string (format:
    "chain_id:url,chain_id:url,...") and provides per-chain hub URL
    resolution with fallback to a default URL.
    """

    def __init__(self, sync_sources: str = "", default_url: str | None = None) -> None:
        """Initialize with config string and default fallback URL.

        Args:
            sync_sources: Comma-separated "chain_id:url" pairs.
            default_url: Fallback URL for chains not in the mapping.
        """
        self._sources: dict[str, str] = self._parse_sync_sources(sync_sources)
        self._default_url = default_url

    @staticmethod
    def _parse_sync_sources(sync_sources: str) -> dict[str, str]:
        """Parse the sync sources config string.

        Format: "chain_id:url,chain_id:url,..."
        Returns dict mapping chain_id → url.
        Raises ValueError for malformed entries.
        """
        if not sync_sources or not sync_sources.strip():
            return {}
        result: dict[str, str] = {}
        for entry in sync_sources.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ValueError(f"Invalid sync source entry (expected 'chain_id:url'): {entry}")
            # Split on first colon only (URL may contain colons)
            chain_id, url = entry.split(":", 1)
            chain_id = chain_id.strip()
            url = url.strip()
            if not chain_id or not url:
                raise ValueError(f"Invalid sync source entry (empty chain_id or url): {entry}")
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"http://{url}"
            result[chain_id] = url
        return result

    def get_sync_source(self, chain_id: str) -> str | None:
        """Resolve sync source URL for a given chain_id.

        1. Check the per-chain mapping
        2. Fall back to default_url
        """
        if chain_id in self._sources:
            return self._sources[chain_id]
        return self._default_url

    def get_all_sources(self) -> dict[str, str]:
        """Return all configured sync sources (chain_id → url)."""
        return dict(self._sources)

    def has_per_chain_sources(self) -> bool:
        """Return True if per-chain sources are configured (non-empty mapping)."""
        return bool(self._sources)
```

Export from `aitbc/sync/__init__.py` as `SyncSourceResolver` (add to existing exports).

#### A2: IslandRegistry

Create `aitbc/network/island_registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IslandRegistryEntry:
    """A single island registry entry mapping island_id to chain and hub."""
    island_id: str
    chain_id: str
    hub_url: str
    island_name: str = ""


class IslandRegistry:
    """Parses the ISLAND_REGISTRY config string and provides lookup.

    Format: "island_id:chain_id:hub_url,island_id:chain_id:hub_url,..."
    Optional 4th field: island_name (defaults to island_id).
    """

    def __init__(self, registry_str: str = "") -> None:
        self._entries: dict[str, IslandRegistryEntry] = self._parse_registry(registry_str)

    @staticmethod
    def _parse_registry(registry_str: str) -> dict[str, IslandRegistryEntry]:
        if not registry_str or not registry_str.strip():
            return {}
        result: dict[str, IslandRegistryEntry] = {}
        for entry in registry_str.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 3:
                raise ValueError(f"Invalid island registry entry (expected 'island_id:chain_id:hub_url'): {entry}")
            island_id = parts[0].strip()
            chain_id = parts[1].strip()
            hub_url = parts[2].strip()
            island_name = parts[3].strip() if len(parts) > 3 else island_id
            if not island_id or not chain_id or not hub_url:
                raise ValueError(f"Invalid island registry entry (empty fields): {entry}")
            if not hub_url.startswith("http://") and not hub_url.startswith("https://"):
                hub_url = f"http://{hub_url}"
            result[island_id] = IslandRegistryEntry(
                island_id=island_id, chain_id=chain_id, hub_url=hub_url, island_name=island_name,
            )
        return result

    def get_entry(self, island_id: str) -> IslandRegistryEntry | None:
        return self._entries.get(island_id)

    def get_all_entries(self) -> list[IslandRegistryEntry]:
        return list(self._entries.values())

    def get_chain_for_island(self, island_id: str) -> str | None:
        entry = self._entries.get(island_id)
        return entry.chain_id if entry else None

    def get_hub_for_island(self, island_id: str) -> str | None:
        entry = self._entries.get(island_id)
        return entry.hub_url if entry else None
```

Export from `aitbc/network/__init__.py` as `IslandRegistry`, `IslandRegistryEntry` (check existing exports first — add to them).

#### A3: Unit tests

**`tests/unit/test_sync_source_resolver.py`**:
- `test_empty_sources_uses_default` — empty string, default URL returned
- `test_single_source` — one chain mapped
- `test_multiple_sources` — multiple chains mapped
- `test_chain_not_in_sources_falls_back` — unknown chain uses default
- `test_no_default_returns_none` — unknown chain, no default → None
- `test_url_normalized_with_http_prefix` — URL without http:// gets prefix
- `test_malformed_entry_raises` — entry without colon raises ValueError
- `test_empty_chain_id_raises` — entry with empty chain_id raises
- `test_has_per_chain_sources` — True when sources configured, False when empty
- `test_get_all_sources` — returns copy of sources dict

**`tests/unit/test_island_registry.py`**:
- `test_empty_registry` — empty string → no entries
- `test_single_entry` — one island parsed correctly
- `test_multiple_entries` — multiple islands
- `test_entry_with_name` — 4th field as island name
- `test_entry_without_name_defaults_to_island_id` — 3 fields, name = island_id
- `test_get_entry` — lookup by island_id
- `test_get_chain_for_island` — chain_id lookup
- `test_get_hub_for_island` — hub_url lookup
- `test_unknown_island_returns_none` — lookup miss
- `test_malformed_entry_raises` — entry with < 3 parts raises ValueError
- `test_url_normalized` — hub_url gets http:// prefix

#### A4: SubscriptionManager

Create `aitbc/network/subscription_manager.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SubscriptionClientProtocol(Protocol):
    """Interface contract for subscription clients (implemented by Agent B)."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def chain_id(self) -> str: ...
    @property
    def hub_url(self) -> str: ...
    @property
    def is_connected(self) -> bool: ...


@dataclass
class SubscriptionEntry:
    """Tracks a single subscription client instance."""
    client: SubscriptionClientProtocol
    task: asyncio.Task[None] | None = None
    restart_count: int = 0
    last_error: str = ""


class SubscriptionManager:
    """Manages multiple subscription clients, one per (chain_id, hub_url) pair.

    Provides lifecycle management: add/remove subscriptions, start/stop all,
    per-subscription restart on failure with configurable backoff.
    """

    def __init__(
        self,
        max_restarts: int = 3,
        restart_delay: float = 5.0,
    ) -> None:
        """Initialize the subscription manager.

        Args:
            max_restarts: Max restart attempts per subscription before giving up.
            restart_delay: Seconds to wait before restarting a failed subscription.
        """
        self._subscriptions: dict[str, SubscriptionEntry] = {}
        self._max_restarts = max_restarts
        self._restart_delay = restart_delay
        self._running = False

    def add_subscription(self, chain_id: str, client: SubscriptionClientProtocol) -> None:
        """Register a subscription client for a chain_id.

        Raises ValueError if a subscription for this chain_id already exists.
        """
        if chain_id in self._subscriptions:
            raise ValueError(f"Subscription for chain_id '{chain_id}' already exists")
        self._subscriptions[chain_id] = SubscriptionEntry(client=client)
        logger.info("Added subscription for chain %s (hub: %s)", chain_id, client.hub_url)

    def remove_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Remove and return a subscription entry. Stops the task if running."""
        entry = self._subscriptions.pop(chain_id, None)
        if entry and entry.task and not entry.task.done():
            entry.task.cancel()
        return entry

    def get_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Get the subscription entry for a chain_id."""
        return self._subscriptions.get(chain_id)

    def get_all_chains(self) -> list[str]:
        """Return all chain_ids with active subscriptions."""
        return list(self._subscriptions.keys())

    async def start_all(self) -> None:
        """Start all registered subscriptions as background tasks."""
        self._running = True
        for chain_id, entry in self._subscriptions.items():
            if entry.task is None or entry.task.done():
                entry.task = asyncio.create_task(
                    self._run_subscription(chain_id), name=f"subscription_{chain_id}",
                )

    async def _run_subscription(self, chain_id: str) -> None:
        """Run a subscription with restart-on-failure logic."""
        entry = self._subscriptions[chain_id]
        while self._running and entry.restart_count <= self._max_restarts:
            try:
                await entry.client.start()
                break  # Normal exit
            except asyncio.CancelledError:
                break
            except Exception as e:
                entry.restart_count += 1
                entry.last_error = str(e)
                logger.warning(
                    "Subscription for chain %s failed (attempt %d/%d): %s",
                    chain_id, entry.restart_count, self._max_restarts, e,
                )
                if entry.restart_count <= self._max_restarts:
                    await asyncio.sleep(self._restart_delay)
                else:
                    logger.error(
                        "Subscription for chain %s exhausted restarts (%d). Giving up.",
                        chain_id, entry.restart_count,
                    )

    async def stop_all(self) -> None:
        """Stop all subscriptions and cancel tasks."""
        self._running = False
        for entry in self._subscriptions.values():
            if entry.task and not entry.task.done():
                entry.task.cancel()
        for entry in self._subscriptions.values():
            if entry.task:
                try:
                    await entry.task
                except asyncio.CancelledError:
                    pass
```

Export from `aitbc/network/__init__.py` as `SubscriptionManager`, `SubscriptionEntry`, `SubscriptionClientProtocol` (add to existing exports).

**`tests/unit/test_subscription_manager.py`**:
- `test_add_subscription` — add one client
- `test_add_duplicate_raises` — adding same chain_id twice raises ValueError
- `test_remove_subscription` — remove and verify task cancelled
- `test_remove_nonexistent_returns_none` — remove miss returns None
- `test_get_subscription` — lookup by chain_id
- `test_get_all_chains` — list of chain_ids
- `test_start_all_starts_tasks` — all clients get tasks
- `test_restart_on_failure` — client fails, gets restarted up to max_restarts
- `test_max_restarts_exhausted` — client fails beyond max, task ends
- `test_stop_all_cancels_tasks` — stop_all cancels all running tasks

---

## Agent B — Apps & Infrastructure

**Scope**: Add per-chain sync source config, multi-hub subscription clients, island manager activation, CLI commands, and integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add config: `chain_sync_sources`, `island_registry`, `gossip_backends`, `island_tasks_enabled` + fail-fast validators | 🔴 P0 | `config.py` | ⬜ |
| B2 | Wire up `SyncSourceResolver` in `main.py` — resolve hub URL per chain | 🔴 P0 | `main.py` | ⬜ |
| B3 | Multi-hub subscription in `main.py` — use `SubscriptionManager` (A4), one client per chain | 🔴 P0 | `main.py`, `subscription_client.py` | ⬜ |
| B4 | Enable island manager background tasks + auto-join islands from config | High | `main.py`, `island_manager.py` | ⬜ |
| B5 | Add `chain sync-status` CLI command — per-chain sync status | Medium | `cli/aitbc_cli/commands/chain.py` | ⬜ |
| B6 | Add `node island health` CLI command + fix `node island list` stub | Medium | `cli/aitbc_cli/commands/node/__init__.py`, `cli/aitbc_cli/commands/node/island.py` | ⬜ |
| B7 | Integration tests — multi-chain sync, multi-hub subscription, island membership | 🔴 P0 | `apps/blockchain-node/tests/test_multi_island.py` (new) | ⬜ |
| B8 | Verify full test suite + mypy + ruff clean | High | — | ⬜ |

### Agent B — Detailed Instructions

#### B1: Add config fields

Add to `config.py` `ChainSettings` class (near existing sync/island settings):

```python
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
# When a background task catches an exception, it sleeps this many seconds
# before retrying. Currently hardcoded to 10s in island_manager.py.
island_task_error_retry_interval: int = 10

# Bridge request expiry in seconds (v0.6.3). Pending bridge requests
# older than this are removed. Currently hardcoded to 3600s (1 hour).
bridge_request_expiry: int = 3600

# Island inactive threshold in seconds (v0.6.3). Islands with 0 peers
# for longer than this are marked INACTIVE. Currently hardcoded to 600s.
island_inactive_threshold: int = 600

# Gossip topic migration (v0.6.3). The v0.6.2 release already subscribes
# to both transactions.{chain_id} and legacy transactions. This config
# controls the migration window and v1 warning logging.
gossip_tx_topic_v1: str = "transactions"
gossip_tx_topic_v2_template: str = "transactions.{chain_id}"
gossip_migration_days: int = 30
gossip_log_v1_warnings: bool = True
```

**Fail-fast config validators** — add `field_validator` methods to the `Settings` class so malformed config is caught at startup, not at runtime:

```python
from pydantic import field_validator

@field_validator("chain_sync_sources")
@classmethod
def validate_chain_sync_sources(cls, v: str) -> str:
    """Fail fast on malformed CHAIN_SYNC_SOURCES at startup."""
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
    """Fail fast on malformed ISLAND_REGISTRY at startup."""
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
    """Fail fast on malformed GOSSIP_BACKENDS at startup."""
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
    """Validate bridge_islands CSV format: UUIDs only, no spaces, no empty entries."""
    if not v or not v.strip():
        return v
    islands = [i.strip() for i in v.split(",") if i.strip()]
    if len(islands) != len(set(islands)):
        raise ValueError(f"Duplicate island_id in bridge_islands: '{v}'")
    for island_id in islands:
        if " " in island_id:
            raise ValueError(f"Invalid bridge_islands entry: '{island_id}'. No spaces allowed (use UUID format)")
    return v
```

**Note**: The `SyncSourceResolver` (A1) and `IslandRegistry` (A2) classes also parse these strings at runtime. The config validators catch malformed config at startup (before any code runs), while the utility classes provide parsing for programmatic use. Both layers validate — defense in depth.

#### B2: Wire up SyncSourceResolver in main.py

1. Import `SyncSourceResolver` from `aitbc.sync`
2. In `BlockchainNode.__init__` or `start()`, create a `SyncSourceResolver`:
   ```python
   self._sync_source_resolver = SyncSourceResolver(
       sync_sources=settings.chain_sync_sources,
       default_url=settings.default_peer_rpc_url,
   )
   ```
3. Add a `get_sync_source(chain_id: str) -> str | None` method:
   ```python
   def get_sync_source(self, chain_id: str) -> str | None:
       return self._sync_source_resolver.get_sync_source(chain_id)
   ```

#### B3: Multi-hub subscription in main.py

Modify the subscription client setup (currently lines 324-334). Uses `SubscriptionManager` from Agent A's A4 task.

**Current** (single client, first chain only):
```python
if settings.subscription_enabled:
    node_id = os.getenv("NODE_ID", settings.p2p_node_id or "unknown-node")
    hub_url = settings.default_peer_rpc_url or settings.genesis_node
    chain_id = self._supported_chains()[0]
    if hub_url:
        subscription_client = SubscriptionClient(hub_url, node_id, chain_id)
        self._task_registry.create_task(subscription_client.start, name="subscription_client")
```

**New** (one client per chain, managed by SubscriptionManager):
```python
from aitbc.network import SubscriptionManager

if settings.subscription_enabled:
    node_id = os.getenv("NODE_ID", settings.p2p_node_id or "unknown-node")
    self._subscription_manager = SubscriptionManager(
        max_restarts=3,
        restart_delay=5.0,
    )
    for chain_id in self._supported_chains():
        hub_url = self.get_sync_source(chain_id)
        if hub_url:
            subscription_client = SubscriptionClient(hub_url, node_id, chain_id)
            self._subscription_manager.add_subscription(chain_id, subscription_client)
            logger.info("Subscription client registered for chain %s via hub %s", chain_id, hub_url)
    # Start all subscriptions as background tasks with restart-on-failure
    await self._subscription_manager.start_all()
```

**SubscriptionClient changes** (in `subscription_client.py`): The existing `SubscriptionClient` class must implement the `SubscriptionClientProtocol` interface from A4:
- Add `chain_id` and `hub_url` as read-only properties (already stored as instance attrs)
- Add `is_connected` property (track WebSocket connection state)
- The `start()` method already exists — no change needed to its signature

**Backward compat**: When `chain_sync_sources` is empty, `get_sync_source()` returns `default_peer_rpc_url` for all chains — same as before but now creates one client per chain (each pointing to the same hub).

#### B4: Enable island manager background tasks

**Island Manager Background Tasks — Documentation (enumerate before enabling)**

The `island_manager.start()` method (island_manager.py:77-87) runs two background tasks. Each must be documented with its purpose, failure recovery, restart behavior, and config before enabling:

| Task | Purpose | Failure Recovery | Restart Behavior | Config |
|------|---------|------------------|------------------|--------|
| `_bridge_request_monitor()` (line 215) | Monitor pending bridge requests, remove expired ones ( >3600s pending) | Catches exceptions, logs error, sleeps 10s, retries | Loop continues on error; task restarts if process restarts; resumes from `bridge_requests` dict state | `bridge_request_monitor_interval: int = 60` (sleep between scans) |
| `_island_health_check()` (line 233) | Periodic health of connected islands — marks islands with 0 peers as INACTIVE after 600s | Catches exceptions, logs error, sleeps 10s, retries | Loop continues on error; task restarts if process restarts; fresh check cycle from `islands` dict | `island_health_check_interval: int = 30` (sleep between checks) |

**Implementation notes**:
- Both tasks use `while self.running:` loops with try/except — they self-heal on transient errors
- The 10s error-retry sleep is hardcoded in island_manager.py:231,249 — make it configurable as `island_task_error_retry_interval: int = 10`
- The 3600s bridge request expiry and 600s inactive threshold are hardcoded — make them configurable as `bridge_request_expiry: int = 3600` and `island_inactive_threshold: int = 600`
- On process restart, both tasks resume from the in-memory `bridge_requests` and `islands` dicts — no persistent state recovery needed (state is rebuilt from P2P handshake peer discovery)

Modify the island manager setup (currently lines 294-310):

1. After `create_island_manager(...)`, if `settings.island_tasks_enabled`:
   ```python
   if settings.island_tasks_enabled:
       await island_manager.start()
       logger.info("Island manager background tasks started")
   else:
       logger.info("Island manager initialized (background tasks disabled)")
   ```

2. Add auto-join logic for islands from `bridge_islands` config:
   ```python
   if settings.bridge_islands and _island_manager_available:
       from aitbc.network import IslandRegistry
       registry = IslandRegistry(settings.island_registry)
       bridge_island_ids = [i.strip() for i in settings.bridge_islands.split(",") if i.strip()]
       for island_id in bridge_island_ids:
           entry = registry.get_entry(island_id)
           if entry:
               island_manager.join_island(
                   island_id=entry.island_id,
                   island_name=entry.island_name,
                   chain_id=entry.chain_id,
                   is_hub=False,
               )
               logger.info("Auto-joined island %s (chain: %s)", entry.island_id, entry.chain_id)
           else:
               logger.warning("Island %s in bridge_islands but not in island_registry", island_id)
   ```

3. The `island_manager.start()` method (island_manager.py:77-87) already runs `_bridge_request_monitor()` and `_island_health_check()`. The intervals should be configurable — modify the `start()` method to use `settings.island_health_check_interval` and `settings.bridge_request_monitor_interval` instead of hardcoded 30s/60s.

**Feature flag**: `settings.island_tasks_enabled` (default `False`).

#### B5: Add `chain sync-status` CLI command

Add to `cli/aitbc_cli/commands/chain.py`:

```python
@chain.command(name="sync-status")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--all-chains", is_flag=True, help="Show status for all supported chains")
def sync_status(node_url, all_chains):
    """Show synchronization status per chain."""
```

Implementation:
- Query `GET /head?chain_id=X` for each chain
- Query `GET /network-info` for supported chains list
- Display per-chain: chain_id, local height, last block hash, sync source URL
- Use `AITBCHTTPClient` from `aitbc_cli.utils.http_client`

#### B6: Add `node island health` + fix `node island list`

**CLI group structure** (verified):
- `aitbc chain sync-status` → `cli/aitbc_cli/commands/chain.py` (top-level `chain` group, already exists with `list`, `status`, `info`, `create`, `delete`, `add`, `remove`, `migrate` subcommands)
- `aitbc node island health` → `cli/aitbc_cli/commands/node/__init__.py` (island group is defined here at line 46-49, with `create`, `join`, `leave`, `list_islands`, `island_info` subcommands)
- `aitbc node island list` (alias) → same file, add `list` as alias for `list_islands`
- The actual command implementations are in `cli/aitbc_cli/commands/node/island.py`

1. Add `health` subcommand to the island group in `cli/aitbc_cli/commands/node/__init__.py`:
   ```python
   @island.command()
   @click.option("--node-url", default="http://127.0.0.1:8202")
   @click.pass_context
   def health(ctx, node_url):
       """Show health status of connected islands."""
       health_island_command(ctx, node_url)
   ```
   - Add `health_island_command` implementation to `cli/aitbc_cli/commands/node/island.py`
   - Query local node for island health (if endpoint exists, or query island manager state)
   - Display: island_id, chain_id, status, peer_count, last_health_check

2. Fix `list_islands_command` in `cli/aitbc_cli/commands/node/island.py` (line 161-174) — replace hardcoded stub with real query:
   - Query `GET /network-info` or a new `/rpc/islands` endpoint
   - If no endpoint available, query the node's island manager state via RPC
   - Display real island data from the node

3. Add `list` as an alias for `list_islands` in `cli/aitbc_cli/commands/node/__init__.py`:
   ```python
   @island.command(name="list")
   @click.pass_context
   def list_islands_alias(ctx):
       """List all known islands (alias for list-islands)."""
       ctx.invoke(list_islands)
   ```

#### B7: Integration tests

Create `apps/blockchain-node/tests/test_multi_island.py`:

```python
class TestSyncSourceResolver:
    """Test per-chain sync source resolution in main.py."""
    def test_single_hub_fallback(self): ...
    def test_per_chain_sources(self): ...
    def test_unknown_chain_uses_default(self): ...

class TestMultiHubSubscription:
    """Test multi-hub subscription client creation."""
    def test_one_client_per_chain(self): ...
    def test_single_chain_backward_compat(self): ...
    def test_no_hub_url_skips_chain(self): ...

class TestIslandManagerActivation:
    """Test island manager background task activation."""
    def test_tasks_disabled_by_default(self): ...
    def test_tasks_enabled_starts_background(self): ...
    def test_auto_join_islands_from_config(self): ...
    def test_auto_join_unknown_island_logged(self): ...

class TestCLICommands:
    """Test new CLI commands."""
    def test_chain_sync_status_help(self): ...
    def test_island_health_help(self): ...
    def test_island_list_alias(self): ...
```

---

## Coordination Protocol

### File Ownership

| File | Owner | Notes |
|------|-------|-------|
| `aitbc/sync/source_resolver.py` | Agent A | A1: new file |
| `aitbc/sync/__init__.py` | Agent A | A1: add export |
| `aitbc/network/island_registry.py` | Agent A | A2: new file |
| `aitbc/network/__init__.py` | Agent A | A2: add export |
| `tests/unit/test_sync_source_resolver.py` | Agent A | A3 |
| `tests/unit/test_island_registry.py` | Agent A | A3 |
| `apps/blockchain-node/src/aitbc_chain/config.py` | Agent B | B1: config additions + validators |
| `apps/blockchain-node/src/aitbc_chain/main.py` | Agent B | B2, B3, B4: sync source, multi-hub sub, island tasks |
| `apps/blockchain-node/src/aitbc_chain/subscription_client.py` | Agent B | B3: multi-hub subscription (see note below) |
| `apps/blockchain-node/src/aitbc_chain/network/island_manager.py` | Agent B | B4: configurable intervals |
| `cli/aitbc_cli/commands/chain.py` | Agent B | B5: sync-status command (top-level `chain` group) |
| `cli/aitbc_cli/commands/node/__init__.py` | Agent B | B6: island health + list alias (island group in node) |
| `cli/aitbc_cli/commands/node/island.py` | Agent B | B6: fix list_islands stub, add health command impl |
| `apps/blockchain-node/tests/test_multi_island.py` | Agent B | B7 |
| `apps/blockchain-node/tests/test_multi_island_design.py` | Agent B | Pre-coding design validation test (write first) |

### Multi-Hub Subscription Client — Interface Contract

The `subscription_client.py` rewrite touches shared infrastructure (WebSocket connections, lease management). To avoid conflicts, the work is split by interface contract:

**Agent A** (core subscription logic — new utility in `aitbc/`):
- `aitbc/network/subscription_manager.py` (new) — generic multi-hub subscription manager
- Tracks multiple `SubscriptionClient` instances by `(chain_id, hub_url)` key
- Provides `add_subscription(chain_id, hub_url)`, `remove_subscription(chain_id)`, `get_subscription(chain_id)`
- Handles per-subscription lifecycle (start, stop, restart on failure)

**Agent B** (WebSocket connection management — in `apps/blockchain-node/`):
- `apps/blockchain-node/src/aitbc_chain/subscription_client.py` — existing file, modify for per-chain use
- WebSocket connection, lease/heartbeat, push message handling
- Consumes `SubscriptionManager` from Agent A

**Coordination**: Agent A defines the `SubscriptionManager` interface first. Agent B implements the WebSocket layer against that interface. Both agents must agree on the interface before implementation begins.

### Dependency Graph

```
Phase 0 (Agent B — write first, before any implementation):
  Pre-coding design test              (validates architecture with stubs)

Phase 1 (Agent A — parallel, no dependencies):
  A1 SyncSourceResolver
  A2 IslandRegistry
  A3 unit tests + verify clean

Phase 2 (Agent B — after A1-A2 are merged):
  B1 config fields + validators       (independent of A)
  B5 chain sync-status CLI            (independent of A)
  B6 island health + list CLI         (independent of A)

Phase 3 (Agent B — after A1-A2 + B1):
  B2 wire up SyncSourceResolver       (depends on A1, B1)
  B3 multi-hub subscription           (depends on A1, B1, B2)
  B4 island manager activation        (depends on A2, B1)

Phase 4 (Agent B — after B2-B4):
  B7 integration tests                (depends on B2, B3, B4)
  B8 final verify                     (depends on all)
```

**Phase 0 (pre-coding test) and B1, B5, B6 can start immediately** (no Agent A dependency). B2-B4 depend on A1-A2. B7-B8 depend on B2-B4.

**Multi-hub subscription client coordination**: Agent A creates `SubscriptionManager` (new utility in `aitbc/network/`). Agent B modifies `subscription_client.py` to consume it. Interface contract must be agreed before implementation.

---

## Success Criteria

- ✅ Per-chain sync source mapping works (CHAIN_SYNC_SOURCES config)
- ✅ One SubscriptionClient per (chain_id, hub_url) pair
- ✅ Island manager background tasks enabled with feature flag
- ✅ Auto-join islands from bridge_islands config
- ✅ `chain sync-status` CLI command works
- ✅ `node island health` CLI command works
- ✅ `node island list` uses real data (not stub)
- ✅ All existing tests pass (546 baseline from v0.6.2)
- ✅ New tests pass (multi-island integration)
- ✅ mypy + ruff clean
- ✅ Backward compatible: single-hub config still works without changes
- ✅ Config validators fail fast on malformed CHAIN_SYNC_SOURCES, ISLAND_REGISTRY, GOSSIP_BACKENDS, bridge_islands
- ✅ Pre-coding design test passes (validates architecture before implementation)
- ✅ **Zero cross-chain block contamination in 24h multi-hub soak test** (blocks from hub-a never appear in chain-b's DB)
