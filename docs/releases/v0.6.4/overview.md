# v0.6.4 — Multi-Chain Per Island Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

## Release Theme

Multi-Chain Per Island — Parallel Block Streams, MultiChainManager Activation, Island-Level Chain Registry.

## Goal

Enable an island to host multiple parallel block streams (chains), each producing blocks independently with its own genesis, block height, state, and mempool — but sharing the same island identity, P2P network, and validator set. Wire up the existing dead-code `MultiChainManager`, make `IslandMembership` hold multiple chain_ids, and activate multi-chain block production within a single island.

> **Scope constraint**: This release activates multi-chain per island only. It does NOT activate `MultiValidatorPoA`/`PBFT` (those stay in THRESHOLD state — separate security review required). It does NOT add bridge functionality (v0.7.0) or inter-chain trading (v0.8.0).

> **Prerequisites**: [v0.6.1](../v0.6.1/change.log) (Parallel Processing — multiple proposers as parallel tasks), [v0.6.3](../v0.6.3/change.log) (Multi-Island Node Support — island-to-chain registry infrastructure). All complete.

> **Risk**: High. The `join_island()` signature change is a breaking change across 5 repos / 8 call sites. Any mismatch crashes island join. Mitigated by: (1) backward compat adapter (`chain_id: str | list[str]`), (2) atomic refactor in single commit, (3) grep verification before merge.

## Status Baseline — Verified Code Targets

| Component | Location | Current State | v0.6.4 Target |
|-----------|----------|---------------|---------------|
| **MultiChainManager** | `apps/blockchain-node/src/aitbc_chain/network/multi_chain_manager.py:61` | Dead code — 0 imports in production. Has `start_chain`, `stop_chain`, `start`, `stop`, `_chain_health_check` | Wire into `main.py` startup |
| **MultiChainManager ports** | `multi_chain_manager.py:90-96` | Sequential allocation from `base+1`, no conflict detection | Add `PortAllocator` with conflict detection |
| **MultiChainManager health** | `multi_chain_manager.py:264-274` | 60s interval, checks ERROR state, logs warnings | Make interval configurable via `MULTI_CHAIN_HEALTH_INTERVAL` |
| **IslandMembership** | `island_manager.py:25-35` | `chain_id: str` (single string) | `chain_ids: list[str]` + `.chain_id` backward compat property |
| **join_island()** | `island_manager.py:94-109` | `join_island(self, island_id, island_name, chain_id: str, is_hub=False) -> bool` | `join_island(self, island_id, island_name, chain_id: str \| list[str], is_hub=False) -> bool` |
| **leave_island()** | `island_manager.py:111-125` | Removes from `islands` + `island_peers` dicts, no chain cleanup | Add chain resource cleanup (databases, proposers, gossip) |
| **MultiValidatorPoA** | `consensus/multi_validator_poa.py:33` | Dead code — 0 production imports, no guards | Add threshold guard (comment + runtime RuntimeError) |
| **PBFT** | `consensus/pbft.py:48` | Dead code — 0 production imports, no guards | Add threshold guard (comment + runtime RuntimeError) |
| **_start_proposers()** | `main.py:406-425` | ✅ **ALREADY supports multiple chains** — creates one `PoAProposer` per chain in `production_chains` | No change needed — coordinate with MultiChainManager |
| **Per-chain databases** | `database.py:197-295` | ✅ **ALREADY supports per-chain** — `session_scope(chain_id)`, `init_db(chain_id)`, `shutdown_db(chain_id)` | No change needed |
| **Gossip topics** | `main.py:149-159` | ✅ **ALREADY chain-specific** — `transactions.{chain_id}` + legacy `transactions` | No change needed |
| **Block hashes** | `poa.py` | ✅ **ALREADY include chain_id** — prevents cross-chain block replay | No change needed |
| **Config — island_chains** | `config.py` | ❌ `island_chains` does NOT exist | Add `island_chains: str` config field |
| **Config — chain_configs** | `config.py` | ❌ `chain_configs` does NOT exist | Add `chain_configs` dict + `field_validator` parser |
| **Config — port offsets** | `config.py` | ❌ `chain_port_offsets` does NOT exist | Add `chain_port_offsets: str` config field |
| **Config — startup retry** | `config.py` | ❌ Multi-chain start retry config does NOT exist | Add `multi_chain_start_max_retries`, `base_delay`, `max_delay`, `backoff_multiplier` |
| **Config — health/shutdown** | `config.py` | ❌ Does NOT exist | Add `multi_chain_health_interval=60`, `chain_shutdown_timeout=10` |
| **CLI — chain start/stop** | `cli/aitbc_cli/commands/chain.py` | ❌ Does NOT exist (chain group has `list`, `status`, `info`, `create`, `delete`, `add`, `remove`, `migrate`, `backup`, `restore`, `monitor`, `sync-status`) | Add `chain start` + `chain stop` subcommands (delegate to `node/chain.py`) |
| **CLI — chain list --island** | `cli/aitbc_cli/commands/chain.py:26` | EXISTS but lacks `--island` flag | Add `--island` option to filter by island |
| **CLI — node chain stubs** | `cli/aitbc_cli/commands/node/chain.py:13-53` | ALL STUBS — `start_chain_command`, `stop_chain_command`, `list_chains_command` return hardcoded mock data | Wire to actual MultiChainManager RPC calls |
| **make_genesis.py** | `apps/blockchain-node/scripts/make_genesis.py` | Single genesis per run, `--chain-id` flag | Add `--island-id` + `--chains` for multi-genesis batch generation |
| **JoinIslandRequest** | `rpc/islands.py:16-23` | `chain_id: str` (single string) | `chain_id: str \| list[str]` (backward compat) |

## Already Implemented (verified — no work needed)

1. ✅ **Multi-chain proposer support** — `main.py:406-425` already creates one `PoAProposer` per chain in `production_chains`, each with its own `session_scope(chain_id)`
2. ✅ **Per-chain databases** — `database.py` already has `session_scope(chain_id)`, `init_db(chain_id)`, `shutdown_db(chain_id)` with per-chain SQLite files
3. ✅ **Per-chain gossip topics** — `main.py:149-159` already subscribes to `transactions.{chain_id}` per chain
4. ✅ **Block hash chain_id** — block hashes already include `chain_id`, preventing cross-chain block replay
5. ✅ **Per-chain mempool** — mempool is already per-chain (namespace includes chain_id)

## Architecture: Multi-Chain Per Island

```
┌──────────────────────────────────────────────────────────────────┐
│ main.py — BlockchainNode.start()                                 │
│                                                                  │
│ 1. Parse ISLAND_CHAINS config → list of chain_ids               │
│ 2. Create MultiChainManager(default_chain, base_db_path, ...)   │
│ 3. Start chains sequentially:                                    │
│    a. Main chain (first in list) — fail fast, no retry           │
│    b. Secondary chains — retry with exponential backoff          │
│ 4. For each chain:                                               │
│    - init_db(chain_id) — per-chain database                      │
│    - MultiChainManager.start_chain(chain_id) — tracks lifecycle  │
│    - PoAProposer created (if in block_production_chains)         │
│    - Gossip subscription to transactions.{chain_id}              │
│ 5. Start multi-chain health monitoring (60s interval)            │
│ 6. Island manager: join_island(chain_ids=[...]) — multi-chain    │
│                                                                  │
│ Backward compat: no ISLAND_CHAINS → single chain (v0.6.3 path)  │
└──────────────────────────────────────────────────────────────────┘
```

## join_island() Caller Inventory (8 call sites — atomic refactor required)

| # | File | Line | Current Signature | Target |
|---|------|------|-------------------|--------|
| 1 | `apps/blockchain-node/src/aitbc_chain/network/island_manager.py` | 94 | `chain_id: str` | `chain_id: str \| list[str]` (implementation) |
| 2 | `apps/blockchain-node/src/aitbc_chain/rpc/islands.py` | 75 | `chain_id=request.chain_id` | Pass `chain_id` (str or list — JoinIslandRequest updated) |
| 3 | `apps/blockchain-node/src/aitbc_chain/main.py` | 329 | `chain_id=entry.chain_id` | Pass `chain_ids=[entry.chain_id]` (from IslandRegistry) |
| 4 | `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | 719 | Forwards to `join_island()` | No change (forwards request) |
| 5 | `apps/edge/src/aitbc_edge/routers/islands.py` | 45 | `chain_id=request.chain_id` | Pass `chain_id` (str or list — JoinIslandRequest updated) |
| 6 | `apps/edge/src/aitbc_edge/services/island_service.py` | 32 | `chain_id: str` | `chain_id: str \| list[str]` |
| 7 | `cli/aitbc_cli/commands/node/island.py` | 39 | `chain_id` (single) | Pass `chain_id` (backward compat adapter handles both) |
| 8 | `packages/py/aitbc-agent-sdk/src/aitbc_agent/edge_api_client.py` | 197 | `chain_id: str` | `chain_id: str \| list[str]` |
| 9 | `apps/coordinator-api/src/app/contexts/infrastructure/routers/islands_proxy.py` | 50 | Pure proxy (forwards body) | No change (forwards request body) |

**Verification before merge**:
```bash
rg "join_island\(" --type=py apps/ cli/ packages/ | grep -v "def join_island" | grep -v __pycache__
```
Must show exactly 8 results, all compatible with new signature.

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/network/port_allocator.py` (new), `aitbc/utils/chain_config.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 9 items | `apps/blockchain-node/` (config, main, island_manager, multi_chain_manager, consensus, rpc, scripts), `cli/`, `apps/edge/`, `packages/py/`, `apps/coordinator-api/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/` utilities. Agent B owns all `apps/`, `cli/`, `packages/` files. Agent B consumes Agent A's utilities.

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.4 — Multi-Chain Per Island
