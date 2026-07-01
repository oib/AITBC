# v0.10.1 — Agent Task Assignment

**Last Updated**: 2026-07-01
**Version**: 1.1 — All tasks complete, post-verification fixes applied

**Release Theme**: Gap Fill — Activate and fix ALL features from v0.6.0–v0.8.2 that were planned but never wired up, deployed, or had broken CLI/RPC integration.

**Goal**: Make existing code actually work. No new features — fix broken CLI commands, misconfigured services, dead-code endpoints, unwired infrastructure, and undeployed services. 20 tasks identified across 9 source releases.

> **Scope**: All fixable gaps from v0.6.0–v0.8.2. 4 architectural gaps deferred to v1.0.0 (parallel block validation, gossip v2 protocol, compact blocks, epoch rewards in block production).

> **Prerequisites**: [v0.10.0](../v0.10.0/change.log) (complete — all critical runtime bugs fixed, features activated).

> **Risk**: Low–Medium. Most tasks are wiring fixes with existing infrastructure. Two tasks (B16 duplicate bridge removal, B18 gossip integration) touch more code. Mitigated by: (1) feature flags for new activations, (2) all changes are to non-functional code, (3) end-to-end verification per task.

---

## Task Split Overview

| Agent | Domain | Tasks | Key Files |
|-------|--------|-------|-----------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/marketplace/blockchain_rpc.py`, `aitbc/governance/types.py`, `tests/unit/` |
| **Agent B** | Apps, CLI, scripts, config | 18 items | `cli/`, `apps/`, `scripts/`, `/etc/aitbc/` |

**Conflict boundary**: Agent A owns `aitbc/` shared core. Agent B owns all `apps/`, `cli/`, `scripts/`. One coordination point: B15 (parameter automation) — Agent A edits `aitbc/governance/types.py` first, then Agent B edits `apps/governance/` to consume the updated types.

**Note**: This is a lopsided release by nature — gap-fill work is predominantly in apps and CLI, not shared core. Agent A has 3 focused tasks; Agent B has 18. Agent A should finish early and assist with verification.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Fix shared core utilities that have bugs or incomplete implementations consumed by apps. Write unit tests for the fixes.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/marketplace/ aitbc/governance/ && ./venv/bin/python -m ruff check aitbc/marketplace/ aitbc/governance/ tests/unit/test_blockchain_rpc_client.py tests/unit/test_governance_types.py && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix `BlockchainRPCClient.verify_escrow()` — use `job_id` instead of `escrow_id` | 🔴 P0 | `aitbc/marketplace/blockchain_rpc.py` | ✅ |
| A2 | Update `ParameterChangeSchema` — remove "deferred to v0.8.x" comment, add `target_service` and `parameter_name` fields for automation | 🟡 P1 | `aitbc/governance/types.py` | ✅ |
| A3 | Unit tests for A1 + A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_blockchain_rpc_client.py` (new), `tests/unit/test_governance_types.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Fix escrow verification parameter mismatch

**File**: `aitbc/marketplace/blockchain_rpc.py`

**Problem**: `verify_escrow()` calls `GET /rpc/escrow/{escrow_id}` but the blockchain endpoint uses `job_id` as the path parameter, not `escrow_id`. This causes 404 errors when the edge service tries to verify escrow.

**Fix**: Change `verify_escrow()` to accept `job_id` (or add a `job_id` parameter) and call `GET /rpc/escrow/{job_id}`. Update the method signature and docstring. Keep backward compatibility by accepting both `escrow_id` (deprecated) and `job_id` parameters.

**Coordination**: Agent B's B9 task updates the edge service to pass `job_id`. Agent A goes first so Agent B can reference the updated signature.

#### A2: Update ParameterChangeSchema for automation

**File**: `aitbc/governance/types.py`

**Problem**: `ParameterChangeSchema` has a comment saying "Parameter automation (actually applying the change to the target service) is deferred to v0.8.x" — but v0.8.x never implemented it. The schema lacks fields needed for the governance service to know which target service to call.

**Fix**:
- Remove the "deferred" comment
- Add `target_service: str` field (values: `"poolhub"`, `"marketplace"`, `"blockchain"`)
- Add `parameter_name: str` field (the parameter key to set)
- Add `parameter_value: str` field (the value to apply)
- Keep existing fields backward compatible

**Coordination**: Agent B's B15 task adds the actual HTTP calls in `governance_service.py`. Agent A goes first so Agent B can reference the updated schema.

#### A3: Unit tests

**Files**: `tests/unit/test_blockchain_rpc_client.py` (new), `tests/unit/test_governance_types.py` (new)

Write unit tests for:
1. `BlockchainRPCClient.verify_escrow()` — verify it calls the correct endpoint with `job_id`
2. `ParameterChangeSchema` — verify new fields are present and validated
3. Backward compatibility — verify old callers still work

Run `mypy`, `ruff`, `pytest` clean for all `aitbc/` changes.

---

## Agent B — Apps, CLI, Scripts & Config

**Scope**: Fix CLI commands, wire infrastructure, deploy services, add missing endpoints, remove duplicate code. 18 tasks across 7 apps and the CLI.

**Working directory**: `/opt/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m mypy --show-error-codes apps/blockchain-node/src/aitbc_chain/ apps/marketplace/ apps/edge/ apps/pool-hub/ apps/governance/ apps/trading/ apps/coordinator-api/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Source | Files | Status |
|---|------|----------|--------|-------|--------|
| B1 | CLI endpoint path fixes — add `/rpc/` prefix | 🔴 P0 | v0.6.2 | `cli/aitbc_cli/commands/sync.py`, `chain.py`, `node/island.py` | ✅ |
| B2 | Island ID "-island" config fix | 🔴 P0 | v0.6.3 | `apps/blockchain-node/src/aitbc_chain/config.py`, `app.py`, `/etc/aitbc/blockchain.env` | ✅ |
| B3 | Node CLI context key fix (`output_format`→`output`) | 🔴 P0 | v0.6.3 | `cli/aitbc_cli/commands/node/*` (5 files) | ✅ |
| B4 | HTTP RPC compression — GZipMiddleware + Accept-Encoding | 🟡 P1 | v0.6.0 | `apps/blockchain-node/src/aitbc_chain/app.py`, `sync.py` | ✅ |
| B5 | P2P→sync peer registration wiring | 🟡 P1 | v0.6.2 | `apps/blockchain-node/src/aitbc_chain/main.py` | ✅ |
| B6 | Enable sync/gossip feature flags | 🟡 P1 | v0.6.2 | `apps/blockchain-node/src/aitbc_chain/config.py`, `/etc/aitbc/blockchain.env` | ✅ |
| B7 | MultiChainManager init in RPC service | 🟡 P1 | v0.6.4 | `apps/blockchain-node/src/aitbc_chain/app.py` | ✅ |
| B8 | Edge-advertise endpoint in marketplace | 🟡 P1 | v0.6.6 | `apps/marketplace/src/marketplace_service/main.py` | ✅ |
| B9 | Edge service escrow verification — use `job_id` | 🟡 P1 | v0.6.6 | `apps/edge/src/aitbc_edge/routers/serve.py`, `schemas/serve.py` | ✅ |
| B10 | Edge node registration on blockchain | 🟠 P2 | v0.6.6 | `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py`, `state/gpu_resources.py`, `apps/edge/src/aitbc_edge/main.py` | ✅ |
| B11 | Edge health monitoring integration | 🟠 P2 | v0.6.6 | `apps/marketplace/src/marketplace_service/main.py`, `domain/marketplace.py` | ✅ |
| B12 | Service payment flow wiring | 🟠 P2 | v0.6.6 | `apps/edge/src/aitbc_edge/config.py`, `routers/serve.py`, `apps/marketplace/src/marketplace_service/services/matching_service.py` | ✅ |
| B13 | Pool join/leave endpoints | 🟡 P1 | v0.6.7 | `apps/pool-hub/src/app/routers/pools.py` | ✅ |
| B14 | Mining RPC endpoints wired to coordinator | 🟡 P1 | v0.6.7 | `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | ✅ |
| B15 | Parameter automation in governance execution | 🟠 P2 | v0.7.4 | `apps/governance/src/governance_service/services/governance_service.py` | ✅ |
| B16 | Remove duplicate bridge implementation | 🟠 P2 | v0.7.4 | `apps/coordinator-api/src/app/contexts/cross_chain/` | ✅ |
| B17 | Deploy trading service | 🔴 P0 | v0.8.0 | `scripts/utils/link-systemd.sh`, systemd | ✅ |
| B18 | Trading service gossip integration | 🟠 P2 | v0.8.2 | `apps/trading/src/trading_service/services/offer_subscription_service.py`, `config.py`, `main.py` | ✅ |
| B19 | Lease tracker integration | 🟠 P2 | v0.8.2 | `apps/trading/src/trading_service/services/offer_subscription_service.py`, `main.py` | ✅ |
| B20 | Polling fallback for offer subscription | 🟠 P2 | v0.8.2 | `apps/trading/src/trading_service/services/offer_subscription_service.py` | ✅ |

### Agent B — Detailed Instructions

#### B1: CLI endpoint path fixes (v0.6.2) — Low risk

**Files**:
- `cli/aitbc_cli/commands/sync.py` — lines 117, 120: add `/rpc/` prefix to `/head` → `/rpc/head`, `/network-info` → `/rpc/network-info`
- `cli/aitbc_cli/commands/chain.py` — lines 584, 612, 667, 693, 719: add `/rpc/` prefix to `/network-info`, `/head`, `/chains/start`, `/chains/stop`, `/chains`
- `cli/aitbc_cli/commands/node/island.py` — lines 167, 204, 240: add `/rpc/` prefix to `/islands`, `/islands/{island_id}`

**Verification**: `aitbc sync status --node-url http://localhost:8202` returns sync info, `aitbc node island list` queries real islands (after B2/B3 also applied)

#### B2: Island ID config fix (v0.6.3) — Low risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/config.py` — add `@model_validator(mode='after')` to `ChainSettings` that defaults `supported_chains` to `chain_id` when empty
- `apps/blockchain-node/src/aitbc_chain/app.py` — line 126: add fallback `or settings.chain_id` to island_id construction: `default_island_id = os.getenv("DEFAULT_ISLAND_ID", f"{(settings.supported_chains.split(',')[0].strip() or settings.chain_id)}-island")`
- `/etc/aitbc/blockchain.env` — add `SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net`

**Verification**: `GET /rpc/islands` returns `island_id: "ait-hub.aitbc.bubuit.net-island"` (not `"-island"`)

#### B3: Node CLI context key fix (v0.6.3) — Low risk

**Files** (replace `ctx.obj.get("output_format", "table")` with `ctx.obj.get("output", "table")` in all):
- `cli/aitbc_cli/commands/node/island.py` — ~9 occurrences
- `cli/aitbc_cli/commands/node/__init__.py` — ~6 occurrences + fix duplicate "list" command (rename first to `list-islands` explicitly)
- `cli/aitbc_cli/commands/node/bridge.py` — ~4 occurrences
- `cli/aitbc_cli/commands/node/monitor.py` — ~2 occurrences
- `cli/aitbc_cli/commands/node/main.py` — ~7 occurrences

**Verification**: `aitbc node island list` runs without crash, `aitbc node list` runs without crash

#### B4: HTTP RPC compression (v0.6.0) — Low risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/app.py` — add `from fastapi.middleware.gzip import GZipMiddleware` and `app.add_middleware(GZipMiddleware, minimum_size=1000)` in `create_app()`
- `apps/blockchain-node/src/aitbc_chain/sync.py` — add `headers={"Accept-Encoding": "gzip, deflate"}` to `httpx.AsyncClient.get()` calls in `fetch_blocks_range()` (~line 309) and remote head fetch (~line 347)

**Note**: `sync.py` is a shared file (Agent B owns, but shared with network layer). No Agent A conflict expected — only adding headers to HTTP calls.

**Verification**: `curl -H "Accept-Encoding: gzip" -s http://localhost:8202/rpc/blocks-range?start=1&end=10 --output - | file -` shows compressed content

#### B5: P2P→sync peer registration wiring (v0.6.2) — Medium risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/main.py` — after ChainSync creation, call `p2p_network.set_peer_capability_callback(sync.register_sync_peer)` to populate `PeerCapabilityTracker` from P2P handshakes. This requires the P2P service to be started in the same process or accessible via callback.

**Verification**: With P2P peers connected, `sync._peer_tracker.get_all_peers()` returns >0 peers. Parallel sync activates when `sync_parallel_enabled=True` (B6) and peers >1.

#### B6: Enable sync/gossip feature flags (v0.6.2) — Low risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/config.py` — change defaults: `sync_delta_enabled: bool = True`, `sync_parallel_enabled: bool = True`, `gossip_priority_enabled: bool = True`
- `/etc/aitbc/blockchain.env` — add explicit flag settings for documentation: `SYNC_DELTA_ENABLED=true`, `SYNC_PARALLEL_ENABLED=true`, `GOSSIP_PRIORITY_ENABLED=true`

**Verification**: `GET /rpc/state/delta?from_height=X&to_height=Y` returns delta, sync uses parallel mode when peers available, gossip messages are prioritized

#### B7: MultiChainManager init in RPC service (v0.6.4) — Medium risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/app.py` — add MultiChainManager init in lifespan (after island manager init, ~line 130):
  ```python
  try:
      from .network.multi_chain_manager import create_multi_chain_manager
      default_chain_id = settings.supported_chains.split(",")[0].strip() or settings.chain_id
      base_db_path = Path(settings.get_db_path(default_chain_id))
      create_multi_chain_manager(
          default_chain_id=default_chain_id,
          base_db_path=base_db_path,
          base_rpc_port=int(os.getenv("RPC_PORT", "8202")),
          base_p2p_port=int(os.getenv("P2P_PORT", "8200")),
      )
      _app_logger.info("Multi-chain manager initialized in RPC service")
  except Exception as e:
      _app_logger.warning("Failed to initialize multi-chain manager: %s", e)
  ```

**Verification**: `GET /rpc/chains` returns chain list (not 503)

#### B8: Edge-advertise endpoint (v0.6.6) — Medium risk

**Files**:
- `apps/marketplace/src/marketplace_service/main.py` — add `POST /v1/marketplace/edge-advertise` endpoint that accepts GPU capabilities from edge nodes (node_id, endpoint, gpu_models, gpu_count, total_vram, region, capabilities) and stores them in the marketplace database

**Verification**: `curl -X POST http://localhost:8102/v1/marketplace/edge-advertise -H "Content-Type: application/json" -d '{"node_id":"edge-1","gpu_models":["RTX 4060"],"gpu_count":1,"total_vram":16,"region":"eu"}'` returns success

#### B9: Edge service escrow verification (v0.6.6) — Low risk

**Depends on**: Agent A's A1 task (fixes `BlockchainRPCClient.verify_escrow()`)

**Files**:
- `apps/edge/src/aitbc_edge/routers/serve.py` — update escrow verification call to pass `job_id` instead of `escrow_id`
- `apps/edge/src/aitbc_edge/schemas/serve.py` — add `job_id: str | None` field to `SubmitComputeRequest`

**Verification**: Edge service escrow verification works against blockchain RPC

#### B10: Edge node registration on blockchain (v0.6.6) — Medium risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py` — add `EdgeNodeRegistration` SQLModel (node_id, endpoint, region, gpu_count, total_vram, capabilities, registered_at, status)
- `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` — add `POST /rpc/edge/register` and `GET /rpc/edge/info/{node_id}` endpoints
- `apps/blockchain-node/src/aitbc_chain/rpc/router.py` — register new edge endpoints
- `apps/edge/src/aitbc_edge/main.py` — call edge registration on startup

**Verification**: `POST /rpc/edge/register` registers edge node on-chain, `GET /rpc/edge/info/{node_id}` returns details

#### B11: Edge health monitoring integration (v0.6.6) — Medium risk

**Files**:
- `apps/marketplace/src/marketplace_service/main.py` — add `GET /v1/marketplace/edge/{node_id}/health` endpoint
- `apps/marketplace/src/marketplace_service/domain/marketplace.py` — populate `health_score` and `last_health_check` from coordinator-api heartbeat data (query coordinator-api `/v1/agents/heartbeat` or similar)

**Verification**: `GET /v1/marketplace/edge/{node_id}/health` returns edge health status

#### B12: Service payment flow wiring (v0.6.6) — Medium risk

**Files**:
- `apps/edge/src/aitbc_edge/config.py` — enable `require_payment_verification=True`
- `apps/edge/src/aitbc_edge/routers/serve.py` — ensure escrow `job_id` is passed from marketplace matching flow
- `apps/marketplace/src/marketplace_service/services/matching_service.py` — pass `job_id` to edge service when assigning tasks

**Verification**: Compute request without valid escrow returns 402, with valid escrow proceeds

#### B13: Pool join/leave endpoints (v0.6.7) — Medium risk

**Files**:
- `apps/pool-hub/src/app/routers/pools.py` — add:
  - `POST /{pool_id}/join` — accepts `miner_id`, `capabilities`, registers miner in pool
  - `POST /{pool_id}/leave` — accepts `miner_id`, removes miner from pool

**Verification**: Miners can join and leave pools via API, pool member count updates

#### B14: Mining RPC endpoints wired to coordinator (v0.6.7) — Medium risk

**Files**:
- `apps/blockchain-node/src/aitbc_chain/rpc/router.py` — replace stub mining endpoints with HTTP calls to coordinator-api:
  - `GET /rpc/mining/miners` → query `COORDINATOR_API_URL/v1/miners`
  - `GET /rpc/mining/status` → aggregate status from coordinator-api

**Note**: `router.py` is a shared file (Agent B owns, Agent A may touch for type fixes). No conflict expected — only replacing stub implementations.

**Verification**: `GET /rpc/mining/miners` returns registered miners from coordinator-api, `GET /rpc/mining/status` shows real mining status

#### B15: Parameter automation in governance (v0.7.4) — Medium risk

**Depends on**: Agent A's A2 task (updates `ParameterChangeSchema` with `target_service`, `parameter_name`, `parameter_value`)

**Files**:
- `apps/governance/src/governance_service/services/governance_service.py` — in `execute_proposal()`, after on-chain tx submission, call target service parameter API based on `target_service`:
  - `"poolhub"` → `POST {POOLHUB_URL}/v1/poolhub/parameters/apply` with `{"parameter_name": ..., "parameter_value": ...}`
  - `"marketplace"` → `POST {MARKETPLACE_URL}/v1/marketplace/parameters/apply` with `{"parameter_name": ..., "parameter_value": ...}`
  - `"blockchain"` → log warning (direct config change not supported via API)
- Add HTTP client and error handling for parameter application failures

**Verification**: Create a governance proposal for a parameter change, execute it, verify the parameter is actually applied to the target service

#### B16: Remove duplicate bridge implementation (v0.7.4) — Medium risk

**Files**:
- `apps/coordinator-api/src/app/contexts/cross_chain/services/cross_chain/bridge_enhanced.py` — remove or mark as deprecated
- `apps/coordinator-api/src/app/contexts/cross_chain/services/cross_chain/bridge.py` — remove or mark as deprecated
- All routers/services that import `CrossChainBridgeService` — migrate to `BridgeClientAdapter`
- Search for all `CrossChainBridgeService` references and update

**Verification**: `grep -r "CrossChainBridgeService" apps/coordinator-api/` returns no active imports, bridge functionality works via `BridgeClientAdapter`

#### B17: Deploy trading service (v0.8.0–v0.8.2) — Low risk

**Files**:
- `scripts/utils/link-systemd.sh` — add `aitbc-trading` to hub service list
- Run: `link-systemd.sh`, `systemctl daemon-reload`, `systemctl enable --now aitbc-trading`
- Verify: `curl http://localhost:8104/health` returns OK

**Verification**: `curl http://localhost:8104/health` returns OK, `aitbc trade chains` returns chain list, `aitbc trade list` returns trades

#### B18: Trading service gossip integration (v0.8.2) — Medium risk

**Files**:
- `apps/trading/src/trading_service/config.py` — add gossip backend config fields: `gossip_backend: str = "redis"`, `gossip_broadcast_url: str = "redis://localhost:6379"`
- `apps/trading/src/trading_service/main.py` — initialize gossip broker connection on startup, create `GossipBroker` instance
- `apps/trading/src/trading_service/services/offer_subscription_service.py` — replace in-memory `asyncio.Queue` mock with actual `gossip_broker.subscribe(f"offers.{chain_id}")` call. Handle incoming gossip events and push to WebSocket subscribers.

**Verification**: Create a marketplace listing on blockchain-node → trading service receives offer event via gossip → WebSocket subscribers get notified

#### B19: Lease tracker integration (v0.8.2) — Medium risk

**Files**:
- `apps/trading/src/trading_service/services/offer_subscription_service.py` — integrate with Redis lease tracker for subscription auth:
  - On subscribe: create lease in Redis with key `lease:offer_subscriber:{node_id}`, TTL = heartbeat interval × 3
  - On heartbeat: renew lease
  - On WebSocket receive: validate lease exists
- `apps/trading/src/trading_service/main.py` — `POST /v1/trading/offers/subscribe` returns real lease expiry from Redis (not fake)

**Verification**: Subscribe to offers → get real lease expiry → heartbeat renews lease → lease expires without heartbeat → subscription dropped

#### B20: Polling fallback for offer subscription (v0.8.2) — Medium risk

**Files**:
- `apps/trading/src/trading_service/services/offer_subscription_service.py` — implement automatic fallback to `OfferSyncService` polling when gossip subscription fails:
  - If gossip subscription disconnects or is silent for `subscription_silent_threshold_multiplier` × heartbeat interval → switch to polling
  - Periodically attempt to re-establish gossip subscription (every 60s)
  - On successful reconnection → switch back to subscription mode
  - Log mode transitions for observability

**Verification**: Disconnect gossip backend → trading service falls back to polling → reconnect gossip → service switches back to subscription mode

---

## Coordination

### Shared files (must be sequenced)

No shared files from the `aitbc/` shared files list are touched in this release. The two `apps/` shared files are Agent B-owned:

| File | Touched by | Notes |
|------|-----------|-------|
| `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | B14 (Agent B) | Replacing stub mining endpoints — no Agent A conflict |
| `apps/blockchain-node/src/aitbc_chain/sync.py` | B4 (Agent B) | Adding Accept-Encoding headers — no Agent A conflict |

### Cross-agent dependencies

| Dependency | Agent A task | Agent B task | Notes |
|-----------|-------------|-------------|-------|
| Escrow param fix | A1 (goes first) | B9 (depends on A1) | Agent A fixes `verify_escrow()` signature, Agent B updates edge service to use it |
| Parameter automation | A2 (goes first) | B15 (depends on A2) | Agent A adds `target_service` field to schema, Agent B adds HTTP calls using it |

### Execution order

1. **Agent A**: A1, A2, A3 (finish first — unblocks B9 and B15)
2. **Agent B**: B1, B2, B3 (CLI fixes — no dependencies)
3. **Agent B**: B4, B5, B6, B7 (infrastructure wiring — no dependencies)
4. **Agent B**: B17 (deploy trading service — no dependencies, unblocks B18-B20)
5. **Agent B**: B8, B9 (depends on A1), B10, B11, B12 (marketplace & edge)
6. **Agent B**: B13, B14 (mining & pool)
7. **Agent B**: B15 (depends on A2), B16 (governance)
8. **Agent B**: B18, B19, B20 (trading service — depends on B17)

---

## Deferred to v1.0.0

| # | Source | Gap | Reason |
|---|--------|-----|--------|
| D1 | v0.6.1 | Parallel block validation, pipeline processing, parallel gas calculation | Block-level architecture redesign |
| D2 | v0.6.2 | Gossip protocol v2 message handling, block propagation pipelining, propagation monitoring, compact blocks | Network protocol redesign |
| D3 | v0.6.7 | Epoch-based rewards wired to block production | Touches consensus — `RewardDistributor` not called in PoA loop |
| D4 | v0.6.3 | Gossip topic migration window (v1→v2 with 30-day timeline) | Low priority — dual-subscribe infrastructure exists |

## Documentation & Operational Items

| # | Source | Item | Owner | Status |
|---|--------|------|-------|--------|
| O1 | v0.7.4 | `docs/architecture/oracle-roadmap.md` missing | Agent B | Create in v0.10.1 |
| O2 | v0.7.5 | 48h testnet soak test pending | — | Schedule after v0.10.1 |
| O3 | v0.7.5 | External security audit not performed | — | Acknowledged — homebrew project |

---

**Documentation Version**: 1.0
**Last Updated**: 2026-07-01
**Release**: v0.10.1 — Gap Fill for v0.6.0–v0.8.2
