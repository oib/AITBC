# v0.6.4 — Agent B Tasks (Apps & Infrastructure)

**Last Updated**: 2026-06-30
**Version**: 1.0

## Scope

Add multi-chain config fields, refactor IslandMembership for multiple chain_ids, atomically update all 8 join_island call sites, wire MultiChainManager into main.py with startup sequencing, add threshold guards to dead consensus code, implement CLI commands, enhance make_genesis.py, and write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
```

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add config fields: `island_chains`, `chain_configs`, `chain_port_offsets`, `multi_chain_start_*`, `multi_chain_health_interval`, `chain_shutdown_timeout` + validators | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py` | ✅ |
| B2 | Refactor `IslandMembership`: `chain_id: str` → `chain_ids: list[str]` + `.chain_id` backward compat property. Update `join_island()` + `leave_island()` | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/network/island_manager.py` | ✅ |
| B3 | Atomic `join_island()` refactor — update all 8 call sites + `JoinIslandRequest` model | 🔴 P0 | `rpc/islands.py`, `main.py`, `rpc/router.py`, `apps/edge/`, `cli/`, `packages/py/`, `apps/coordinator-api/` | ✅ |
| B4 | Wire `MultiChainManager` into `main.py` — startup sequencing with retry/backoff, per-chain port allocation via `PortAllocator` (A1) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/main.py`, `network/multi_chain_manager.py` | ✅ |
| B5 | Add threshold guards to `MultiValidatorPoA` + `PBFT` (comment + runtime RuntimeError) | High | `consensus/multi_validator_poa.py`, `consensus/pbft.py` | ✅ |
| B6 | CLI: `chain start` + `chain stop` (delegate to `node/chain.py`), `chain list --island`, wire `node/chain.py` stubs to real RPC | Medium | `cli/aitbc_cli/commands/chain.py`, `cli/aitbc_cli/commands/node/chain.py` | ✅ |
| B7 | `make_genesis.py` multi-genesis support — `--island-id` + `--chains` flags | Medium | `apps/blockchain-node/scripts/make_genesis.py` | ✅ |
| B8 | Integration tests — multi-chain block production, island leave cleanup, backward compat | 🔴 P0 | `apps/blockchain-node/tests/test_v064_multi_chain.py` (new) | ✅ |
| B9 | Verify full test suite + mypy + ruff clean | High | — | ✅ |

## Detailed Instructions

### B1: Add config fields

Add to `config.py` `ChainSettings` class (after existing island config at line 200, before v0.6.3 fields at line 205):

```python
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
```

Add `field_validator` for `chain_configs`:
```python
from aitbc.utils.chain_config import ChainConfigParser

@field_validator("chain_configs", mode="before")
@classmethod
def parse_chain_configs(cls, v: dict[str, str] | str) -> dict[str, str]:
    """Validate chain_configs dict. Values are raw config strings
    parsed later by ChainConfigParser at point of use."""
    if not v:
        return {}
    if isinstance(v, str):
        # If passed as string, try to parse as JSON
        import json
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            raise ValueError(f"chain_configs must be a dict or JSON string, got: {v}") from None
    # Validate each value is a non-empty string
    for chain_id, config_str in v.items():
        if not isinstance(config_str, str):
            raise ValueError(f"chain_configs['{chain_id}'] must be a string, got: {type(config_str)}")
        if config_str.strip():
            # Validate parseable by ChainConfigParser
            ChainConfigParser.parse(config_str)
    return v
```

**Note**: The `chain_configs` validator validates that config strings are parseable but stores them as raw strings. The actual parsing into typed dicts happens at point of use (in `MultiChainManager` or `_proposer_config()`).

### B2: Refactor IslandMembership

In `apps/blockchain-node/src/aitbc_chain/network/island_manager.py`:

**IslandMembership** (lines 25-35) — change `chain_id: str` to `chain_ids: list[str]`:
```python
@dataclass
class IslandMembership:
    island_id: str
    island_name: str
    chain_ids: list[str]       # ← was chain_id: str
    status: IslandStatus
    joined_at: float
    is_hub: bool = False
    peer_count: int = 0

    @property
    def chain_id(self) -> str:
        """Backward compat: returns first chain_id."""
        return self.chain_ids[0] if self.chain_ids else ""
```

**join_island()** (line 94) — accept `str | list[str]`:
```python
def join_island(
    self, island_id: str, island_name: str, chain_id: str | list[str], is_hub: bool = False
) -> bool:
    """Join an island. Accepts single chain_id (str) or multiple chain_ids (list)."""
    if island_id in self.islands:
        logger.warning("Already member of island %s", island_id)
        return False
    chain_ids = [chain_id] if isinstance(chain_id, str) else list(chain_id)
    if not chain_ids:
        logger.warning("Cannot join island %s with empty chain_ids", island_id)
        return False
    self.islands[island_id] = IslandMembership(
        island_id=island_id,
        island_name=island_name,
        chain_ids=chain_ids,
        status=IslandStatus.ACTIVE,
        joined_at=time.time(),
        is_hub=is_hub,
    )
    self.island_peers[island_id] = set()
    logger.info("Joined island %s (name: %s, chains: %s)", island_id, island_name, chain_ids)
    return True
```

**leave_island()** (line 111) — add chain resource cleanup:
```python
def leave_island(self, island_id: str) -> bool:
    """Leave an island. Cleans up all chain memberships."""
    if island_id == self.default_island_id:
        logger.warning("Cannot leave default island")
        return False
    if island_id not in self.islands:
        logger.warning("Not member of island %s", island_id)
        return False
    membership = self.islands[island_id]
    # Clean up chain resources
    for chain_id in membership.chain_ids:
        try:
            shutdown_db(chain_id)
            logger.info("Shut down database for chain %s on island %s", chain_id, island_id)
        except Exception as e:
            logger.warning("Failed to shut down database for chain %s: %s", chain_id, e)
    if island_id in self.active_bridges:
        self.active_bridges.remove(island_id)
    del self.islands[island_id]
    if island_id in self.island_peers:
        del self.island_peers[island_id]
    logger.info("Left island %s (cleaned up %d chains)", island_id, len(membership.chain_ids))
    return True
```

**_initialize_default_island()** (line 64) — update to use `chain_ids`:
```python
def _initialize_default_island(self) -> None:
    self.islands[self.default_island_id] = IslandMembership(
        island_id=self.default_island_id,
        island_name="default",
        chain_ids=[self.default_chain_id],  # ← was chain_id=self.default_chain_id
        status=IslandStatus.ACTIVE,
        joined_at=time.time(),
        is_hub=False,
    )
    self.island_peers[self.default_island_id] = set()
```

**approve_bridge_request()** (line 145) — update any `chain_id=` to `chain_ids=`:
```python
# In approve_bridge_request, where it creates a new IslandMembership:
chain_ids=[bridge_chain_id],  # ← was chain_id=bridge_chain_id
```

### B3: Atomic join_island refactor

Update all 8 call sites in a **single commit**. The backward compat adapter in B2 (`chain_id: str | list[str]`) means most callers can continue passing a single string — only callers that need multi-chain should pass a list.

**Files to update**:

1. **`rpc/islands.py:16-23`** — Update `JoinIslandRequest`:
   ```python
   class JoinIslandRequest(BaseModel):
       island_id: str
       island_name: str
       chain_id: str | list[str]  # ← was chain_id: str
       role: str = "compute-provider"
       is_hub: bool = False
   ```
   The call at line 75 (`island_manager.join_island(...)`) needs no change — it passes `chain_id=request.chain_id` which now accepts both types.

2. **`main.py:329`** — Auto-join bridge islands. Change to pass list:
   ```python
   island_mgr.join_island(
       island_id=entry.island_id,
       island_name=entry.island_name,
       chain_id=entry.chain_id,  # Still single string — backward compat adapter handles it
       is_hub=False,
   )
   ```
   No change needed — backward compat adapter handles single string.

3. **`rpc/router.py:719`** — Pure route handler, forwards to `join_island()`. No change needed.

4. **`apps/edge/src/aitbc_edge/routers/islands.py:13,45`** — Update `JoinIslandRequest`:
   ```python
   class JoinIslandRequest(BaseModel):
       island_id: str
       island_name: str
       chain_id: str | list[str]  # ← was chain_id: str
       role: str = "compute-provider"
       is_hub: bool = False
   ```

5. **`apps/edge/src/aitbc_edge/services/island_service.py:32`** — Update signature:
   ```python
   async def join_island(
       self, island_id: str, island_name: str, chain_id: str | list[str],
       role: str = "compute-provider", is_hub: bool = False
   ) -> dict[str, Any]:
   ```

6. **`cli/aitbc_cli/commands/node/island.py:39`** — No change needed (passes single string, backward compat adapter handles it).

7. **`packages/py/aitbc-agent-sdk/src/aitbc_agent/edge_api_client.py:197`** — Update signature:
   ```python
   async def join_island(
       self, island_id: str, island_name: str, chain_id: str | list[str],
       role: str = "compute-provider", is_hub: bool = False
   ) -> dict[str, Any]:
   ```
   Update JSON body:
   ```python
   json={"island_id": island_id, "island_name": island_name, "chain_id": chain_id, "role": role, "is_hub": is_hub},
   ```

8. **`apps/coordinator-api/src/app/contexts/infrastructure/routers/islands_proxy.py:50`** — Pure proxy, no change needed.

**Verification** (run before committing B3):
```bash
rg "join_island\(" --type=py apps/ cli/ packages/ | grep -v "def join_island" | grep -v __pycache__
# Must show 8 results, all compatible with new signature
```

### B4: Wire MultiChainManager into main.py

In `apps/blockchain-node/src/aitbc_chain/main.py`:

1. Import `MultiChainManager` and `PortAllocator`:
   ```python
   from .network.multi_chain_manager import MultiChainManager
   from aitbc.network import PortAllocator
   ```

2. In `BlockchainNode.start()`, after chain database init (line 297-301), add MultiChainManager setup:
   ```python
   # Parse ISLAND_CHAINS config
   island_chains_str = getattr(settings, "island_chains", "")
   if island_chains_str:
       island_chains = [c.strip() for c in island_chains_str.split(",") if c.strip()]
   else:
       island_chains = self._supported_chains()  # Backward compat: use supported_chains

   # Create port allocator
   port_allocator = PortAllocator(
       base_rpc_port=settings.rpc_bind_port,
       base_p2p_port=settings.p2p_bind_port,
       port_offsets=settings.chain_port_offsets,
   )

   # Create multi-chain manager
   self._multi_chain_manager = MultiChainManager(
       default_chain_id=island_chains[0],
       base_db_path=settings.get_db_path(),
       base_rpc_port=settings.rpc_bind_port,
       base_p2p_port=settings.p2p_bind_port,
   )

   # Start chains sequentially with retry/backoff
   await self._start_chains_sequentially(island_chains)
   ```

3. Add `_start_chains_sequentially` method:
   ```python
   async def _start_chains_sequentially(self, chain_ids: list[str]) -> None:
       """Start chains sequentially. Main chain fails fast, secondary chains retry."""
       if not chain_ids:
           return
       # Main chain — fail fast
       main_chain = chain_ids[0]
       try:
           init_db(main_chain)
           await self._multi_chain_manager.start_chain(main_chain)
           logger.info("Main chain %s started successfully", main_chain)
       except Exception as e:
           logger.error("Main chain %s failed to start: %s — aborting", main_chain, e)
           raise

       # Secondary chains — retry with backoff
       for chain_id in chain_ids[1:]:
           for attempt in range(settings.multi_chain_start_max_retries + 1):
               try:
                   init_db(chain_id)
                   await self._multi_chain_manager.start_chain(chain_id)
                   logger.info("Chain %s started successfully (attempt %d)", chain_id, attempt + 1)
                   break
               except Exception as e:
                   if attempt == settings.multi_chain_start_max_retries:
                       logger.error("Chain %s failed to start after %d attempts: %s", chain_id, attempt + 1, e)
                       break
                   delay = min(
                       settings.multi_chain_start_base_delay * (settings.multi_chain_start_backoff_multiplier ** attempt),
                       settings.multi_chain_start_max_delay,
                   )
                   logger.warning("Chain %s start attempt %d failed, retrying in %.1fs: %s", chain_id, attempt + 1, delay, e)
                   await asyncio.sleep(delay)

       # Start multi-chain health monitoring
       self._task_registry.create_task(self._multi_chain_manager.start, name="multi_chain_manager")
   ```

4. Update island manager join to pass chain_ids list:
   ```python
   # In the island manager auto-join section (line 329):
   island_mgr.join_island(
       island_id=entry.island_id,
       island_name=entry.island_name,
       chain_id=entry.chain_id,  # Backward compat: single string → [string]
       is_hub=False,
   )
   ```

5. Update `MultiChainManager._chain_health_check()` to use configurable interval:
   ```python
   # In multi_chain_manager.py, line 264-274:
   async def _chain_health_check(self) -> None:
       while True:
           await asyncio.sleep(settings.multi_chain_health_interval)  # ← was hardcoded 60
           for chain_id, chain in self.chains.items():
               if chain.status == ChainStatus.ERROR:
                   logger.warning("Chain %s in ERROR state: %s", chain_id, chain.error_message)
   ```

### B5: Threshold guards

**`consensus/multi_validator_poa.py`** — add after module docstring (line 4):
```python
# ════════════════════════════════════════════════════════════════
# THRESHOLD STATE — DO NOT ACTIVATE WITHOUT SECURITY REVIEW
# Requires: validator rotation, slashing, multi-validator consensus audit
# Activation: set MULTI_VALIDATOR_CONSENSUS_ENABLED=true (NOT in this release)
# See: v0.7.x security releases for activation plan
# ════════════════════════════════════════════════════════════════
```

Add runtime guard in `__init__` (line 36):
```python
def __init__(self, chain_id: str):
    import os
    if os.getenv("MULTI_VALIDATOR_CONSENSUS_ENABLED", "").lower() != "true":
        raise RuntimeError(
            "MultiValidatorPoA is in THRESHOLD state and not yet activated. "
            "Set MULTI_VALIDATOR_CONSENSUS_ENABLED=true to override (requires security review)."
        )
    self.chain_id = chain_id
    # ... rest of existing init
```

**`consensus/pbft.py`** — add after module docstring (line 4):
```python
# ════════════════════════════════════════════════════════════════
# THRESHOLD STATE — DO NOT ACTIVATE WITHOUT SECURITY REVIEW
# Requires: validator rotation, slashing, multi-validator consensus audit
# Activation: set MULTI_VALIDATOR_CONSENSUS_ENABLED=true (NOT in this release)
# See: v0.7.x security releases for activation plan
# ════════════════════════════════════════════════════════════════
```

Add runtime guard in `__init__` (line 51):
```python
def __init__(self, consensus: MultiValidatorPoA):
    import os
    if os.getenv("MULTI_VALIDATOR_CONSENSUS_ENABLED", "").lower() != "true":
        raise RuntimeError(
            "PBFTConsensus is in THRESHOLD state and not yet activated. "
            "Set MULTI_VALIDATOR_CONSENSUS_ENABLED=true to override (requires security review)."
        )
    self.consensus = consensus
    # ... rest of existing init
```

**Note**: Existing tests in `consensus/test_multi_validator_poa.py` will need the env var set. Add a fixture or conftest.py entry:
```python
# In tests/conftest.py or consensus/conftest.py:
import os
os.environ["MULTI_VALIDATOR_CONSENSUS_ENABLED"] = "true"  # For tests only
```

### B6: CLI commands

**`cli/aitbc_cli/commands/chain.py`** — add `start` and `stop` subcommands:

```python
from .node.chain import start_chain_command, stop_chain_command

@chain.command(name="start")
@click.argument("chain_id")
@click.option("--chain-type", type=click.Choice(["bilateral", "micro"]), default="micro")
@click.pass_context
def start(ctx, chain_id, chain_type):
    """Start a chain (delegates to node chain start)."""
    start_chain_command(ctx, chain_id, chain_type)

@chain.command(name="stop")
@click.argument("chain_id")
@click.pass_context
def stop(ctx, chain_id):
    """Stop a chain (delegates to node chain stop)."""
    stop_chain_command(ctx, chain_id)
```

Add `--island` option to existing `list` command (line 26):
```python
@chain.command(name="list")
@click.option("--type", "chain_type", help="Filter by chain type")
@click.option("--show-private", is_flag=True, help="Show private chains")
@click.option("--sort", type=click.Choice(["name", "height", "peers"]), default="name")
@click.option("--island", "island_id", default=None, help="Filter by island ID")
@click.pass_context
def list_chains(ctx, chain_type, show_private, sort, island_id):
    # ... existing logic ...
    if island_id:
        # Filter chains by island (query node's /rpc/islands or /network-info)
        # TODO: implement island filter via RPC
        pass
```

**`cli/aitbc_cli/commands/node/chain.py`** — wire stubs to real RPC:

Replace stub `start_chain_command` (lines 13-29) with RPC call:
```python
def start_chain_command(ctx, chain_id, chain_type):
    """Start a new parallel chain instance"""
    try:
        node_url = ctx.obj.get("node_url", "http://127.0.0.1:8202")
        import httpx
        with httpx.Client() as client:
            response = client.post(
                f"{node_url}/rpc/chains/start",
                json={"chain_id": chain_id, "chain_type": chain_type},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
        output(result, ctx.obj.get("output_format", "table"), title=f"Starting Chain: {chain_id}")
        success(f"Chain {chain_id} started successfully")
    except Exception as e:
        error(f"Error starting chain: {str(e)}")
        raise click.Abort() from e
```

Replace stub `stop_chain_command` (lines 32-39) with RPC call:
```python
def stop_chain_command(ctx, chain_id):
    """Stop a parallel chain instance"""
    try:
        node_url = ctx.obj.get("node_url", "http://127.0.0.1:8202")
        import httpx
        with httpx.Client() as client:
            response = client.post(
                f"{node_url}/rpc/chains/stop",
                json={"chain_id": chain_id},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
        success(f"Chain {chain_id} stopped successfully")
    except Exception as e:
        error(f"Error stopping chain: {str(e)}")
        raise click.Abort() from e
```

Replace stub `list_chains_command` (lines 42-53) with RPC call:
```python
def list_chains_command(ctx):
    """List all active chain instances"""
    try:
        node_url = ctx.obj.get("node_url", "http://127.0.0.1:8202")
        import httpx
        with httpx.Client() as client:
            response = client.get(f"{node_url}/rpc/chains", timeout=10.0)
            response.raise_for_status()
            chains = response.json().get("chains", [])
        output(chains, ctx.obj.get("output_format", "table"), title="Active Chains")
    except Exception as e:
        error(f"Error listing chains: {str(e)}")
        raise click.Abort() from e
```

**Note**: The RPC endpoints (`/rpc/chains/start`, `/rpc/chains/stop`, `/rpc/chains`) need to be added to `rpc/router.py` if they don't exist. Check first — if MultiChainManager is wired in B4, add corresponding RPC routes.

### B7: make_genesis.py multi-genesis

In `apps/blockchain-node/scripts/make_genesis.py`:

Add `--island-id` and `--chains` flags:
```python
parser.add_argument(
    "--island-id",
    default=None,
    help="Island ID for multi-genesis generation (generates one genesis per chain)",
)
parser.add_argument(
    "--chains",
    default=None,
    help="Comma-separated list of chain IDs for multi-genesis generation",
)
parser.add_argument(
    "--output-dir",
    default=None,
    help="Output directory for multi-genesis (one subdirectory per chain)",
)
```

Update `main()` to handle multi-genesis:
```python
if args.island_id and args.chains:
    # Multi-genesis mode
    chain_ids = [c.strip() for c in args.chains.split(",") if c.strip()]
    output_dir = Path(args.output_dir or "data")
    for chain_id in chain_ids:
        genesis = build_genesis(chain_id, allocations, authorities)
        genesis["island_id"] = args.island_id  # Add island metadata
        genesis_path = output_dir / chain_id / "genesis.json"
        write_genesis(genesis_path, genesis, args.force)
        print(f"[genesis] chain {chain_id}: {genesis_path}")
else:
    # Single genesis mode (backward compat — existing --chain-id path)
    genesis = build_genesis(args.chain_id, allocations, authorities)
    write_genesis(args.output, genesis, args.force)
```

**Backward compat**: `--chain-id` still works exactly as before. `--island-id` + `--chains` activates multi-genesis mode.

### B8: Integration tests

Create `apps/blockchain-node/tests/test_v064_multi_chain.py`:

**Test cases**:
1. `test_island_membership_multiple_chains` — `IslandMembership.chain_ids` holds multiple chain_ids
2. `test_join_island_with_list` — `join_island(chain_id=["chain-a", "chain-b"])` works
3. `test_join_island_with_single_string_backward_compat` — `join_island(chain_id="chain-a")` still works
4. `test_leave_island_cleans_up_all_chains` — leave island with 3 chains → verify all databases shut down
5. `test_island_membership_chain_id_property` — `.chain_id` returns `chain_ids[0]`
6. `test_multi_chain_manager_start_stop` — start/stop individual chains
7. `test_multi_chain_manager_health_check` — health monitoring reports per-chain status
8. `test_port_allocator_no_conflicts` — 5 chains with different offsets, no port conflicts
9. `test_port_allocator_conflict_detection` — two chains with same offset raises PortAllocationError
10. `test_multi_genesis_generation` — `make_genesis.py --island-id --chains` generates correct files
11. `test_backward_compat_single_chain_config` — no `ISLAND_CHAINS` config → single chain works
12. `test_backward_compat_make_genesis_chain_id` — `--chain-id` flag still works
13. `test_threshold_guard_multi_validator_poa` — instantiating MultiValidatorPoA without env var raises RuntimeError
14. `test_threshold_guard_pbft` — instantiating PBFTConsensus without env var raises RuntimeError
15. `test_chain_config_parser_validates` — malformed CHAIN_CONFIG entries fail fast

### B9: Verify full test suite

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Expected: 190+ passed (existing + new A1-A3 tests)

cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/ -q -o addopts="" --timeout=60
# Expected: 442+ passed, 17 skipped, 1 xfailed (existing + new B8 tests)

cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: 0 errors

cd /opt/aitbc && ./venv/bin/python -m ruff check .
# Expected: All checks passed
```

## Dependency Graph

```
Phase 1 (parallel):
  A1: PortAllocator ─────────────┐
  A2: ChainConfigParser ─────────┤
  A3: Unit tests for A1-A2 ──────┘
                                 │
Phase 2 (sequential, depends on A1-A2):
  B1: Config fields ─────────────┐
  B2: IslandMembership refactor ─┤
                                 │
Phase 3 (depends on B2):         │
  B3: Atomic join_island refactor┤
  B5: Threshold guards ──────────┤
                                 │
Phase 4 (depends on B1, A1):     │
  B4: MultiChainManager wiring ──┤
                                 │
Phase 5 (depends on B4):         │
  B6: CLI commands ──────────────┤
  B7: make_genesis multi ────────┤
                                 │
Phase 6 (depends on all):        │
  B8: Integration tests ─────────┤
  B9: Final verification ────────┘
```

## Coordination

- **Agent A** goes first (Phase 1) — creates `PortAllocator` and `ChainConfigParser` in `aitbc/`.
- **Agent B** starts Phase 2 after Agent A's Phase 1 is complete (B1 needs `ChainConfigParser`, B4 needs `PortAllocator`).
- **B3 (atomic join_island refactor)** must be a single commit — all 8 call sites updated together.
- **B5 (threshold guards)** may break existing tests in `consensus/test_multi_validator_poa.py` — set `MULTI_VALIDATOR_CONSENSUS_ENABLED=true` in test conftest.

## Success Criteria

- ✅ Island hosts 2+ chains producing blocks simultaneously
- ✅ Each chain has independent block height, state, and mempool
- ✅ MultiChainManager activated and managing chain lifecycle
- ✅ `IslandMembership` holds multiple chain_ids (with `.chain_id` backward compat)
- ✅ Dynamic chain start/stop works without node restart
- ✅ Per-chain genesis generation works (`--island-id` + `--chains`)
- ✅ Backward compatible: single-chain config still works
- ✅ All 8 join_island call sites updated atomically (grep verified)
- ✅ MultiValidatorPoA/PBFT have threshold guards (runtime + comment)
- ✅ Startup sequencing with retry/backoff for secondary chains
- ✅ Per-chain port allocation with conflict detection
- ✅ CHAIN_CONFIG_ parsing validator fails fast on malformed entries
- ✅ Island leave cleans up all chain resources (databases, proposers, gossip)
- ✅ Zero port conflicts across 5+ chains on single island
- ✅ All existing tests pass (190 unit + 442 blockchain-node)
- ✅ New tests pass (multi-chain integration)
- ✅ mypy: 0 errors
- ✅ ruff: clean

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.4 — Multi-Chain Per Island
**Agent**: Agent B (Apps & Infrastructure)
