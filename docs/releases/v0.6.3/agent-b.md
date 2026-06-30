# v0.6.3 — Agent B Tasks (Apps & Infrastructure)

**Last Updated**: 2026-06-30
**Version**: 1.0

## Scope

Add per-chain sync source config, multi-hub subscription clients, island manager activation, CLI commands, and integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add config: `chain_sync_sources`, `island_registry`, `gossip_backends`, `island_tasks_enabled` + fail-fast validators | 🔴 P0 | `config.py` | ✅ |
| B2 | Wire up `SyncSourceResolver` in `main.py` — resolve hub URL per chain | 🔴 P0 | `main.py` | ✅ |
| B3 | Multi-hub subscription in `main.py` — use `SubscriptionManager` (A4), one client per chain | 🔴 P0 | `main.py`, `subscription_client.py` | ✅ |
| B4 | Enable island manager background tasks + auto-join islands from config | High | `main.py`, `island_manager.py` | ✅ |
| B5 | Add `chain sync-status` CLI command — per-chain sync status | Medium | `cli/aitbc_cli/commands/chain.py` | ✅ |
| B6 | Add `node island health` CLI command + fix `node island list` stub | Medium | `cli/aitbc_cli/commands/node/__init__.py`, `cli/aitbc_cli/commands/node/island.py` | ✅ |
| B7 | Integration tests — multi-chain sync, multi-hub subscription, island membership | 🔴 P0 | `apps/blockchain-node/tests/test_v063_multi_island.py` (new) | ✅ |
| B8 | Verify full test suite + mypy + ruff clean | High | — | ✅ |

## Detailed Instructions

### B1: Add config fields

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

### B2: Wire up SyncSourceResolver in main.py

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

### B3: Multi-hub subscription in main.py

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

### B4: Enable island manager background tasks

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

### B5: Add `chain sync-status` CLI command

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

### B6: Add `node island health` + fix `node island list`

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

### B7: Integration tests

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

### B8: Verify full test suite

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
# Expected: 546+ passed (existing + new B7 tests)

cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: 0 errors

cd /opt/aitbc && ./venv/bin/python -m ruff check .
# Expected: All checks passed
```

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.3 — Multi-Island Node Support
**Agent**: Agent B (Apps & Infrastructure)
