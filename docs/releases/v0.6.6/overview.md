# v0.6.6 Compute Marketplace — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Compute Marketplace — GPU Offers, Edge Serving, Marketplace Matching, Blockchain-Backed Service Registration.

**Goal**: Connect the marketplace, GPU, and edge services into a functioning compute marketplace. Add chain_id awareness to offer discovery, implement a formal offer state machine, add payment verification to edge serving, and integrate marketplace matching with agent-coordinator task queues.

> **Scope constraint**: This release targets `apps/marketplace/` (~2K lines), `apps/gpu/` (~1.2K lines), `apps/edge/` (~1.4K lines), and new shared utilities in `aitbc/`. It does NOT add reputation scoring (v0.6.7), pool hub/mining (v0.6.7), or bridge functionality (v0.7.0).

> **Prerequisites**: [v0.6.5](../v0.6.5/change.log) (Agent Coordination — task assignment, PaymentEscrow), [v0.6.3](../v0.6.3/change.log) (Multi-Island), [v0.6.4](../v0.6.4/change.log) (Multi-Chain Per Island), [v0.5.16](../v0.5.16/change.log) (chain_id-aware transactions). All verified complete.

> **Risk**: Medium. Changes are backward compatible (optional chain_id, feature-flagged payment). Schema fixes in edge service are breaking but the existing code is already broken (runtime errors from schema mismatch). Mitigated by: (1) all offer FSM changes are additive, (2) payment verification is feature-flagged, (3) edge schema fixes fix already-broken code.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (OfferFSM, BlockchainRPCClient, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (marketplace, GPU, edge services integration)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation)
- [Already Fixed](#already-fixed-verified--no-work-needed)
- [Architecture: Compute Marketplace with Chain Awareness](#architecture-compute-marketplace-with-chain-awareness)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [OfferFSM](./agent-a.md#a1-offerfsm)
- [BlockchainRPCClient](./agent-a.md#a2-blockchainrpcclient)
- [Unit tests](./agent-a.md#a3-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Marketplace config](./agent-b.md#b1-marketplace-config)
- [GPU service config](./agent-b.md#b2-gpu-service-config)
- [Marketplace integration](./agent-b.md#b3-marketplace-use-blockchainrpcclient-a1)
- [GPU service integration](./agent-b.md#b4-gpu-service-use-blockchainrpcclient-a1)
- [Edge service fixes](./agent-b.md#b5-edge-service-fix-schema-mismatches)
- [Marketplace matching](./agent-b.md#b6-marketplace-matching)
- [Integration tests](./agent-b.md#b7-integration-tests)
- [Verify full test suite](./agent-b.md#b8-verify-full-test-suite--ruff--mypy-clean)

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Component | Location | Current State | v0.6.6 Target |
|-----------|----------|---------------|---------------|
| **Marketplace config** | `apps/marketplace/src/marketplace_service/main.py:19` | ❌ No Settings class, `BLOCKCHAIN_RPC_URL` defaults to `http://localhost:8006` (stale port) | Add Settings class, fix port to 8202, add `DEFAULT_CHAIN_ID`, `AGENT_COORDINATOR_URL` |
| **Marketplace RPC** | `apps/marketplace/src/marketplace_service/services/marketplace_service.py:206-276` | ✅ Uses RPC (not direct DB), but no chain_id in queries | Add chain_id filter to RPC queries |
| **Marketplace matching** | `apps/marketplace/src/marketplace_service/services/matching_service.py:21-98` | Basic scoring only, no agent-coordinator integration | Price-time priority matching + agent-coordinator task queue integration |
| **Marketplace offer FSM** | `apps/marketplace/src/marketplace_service/domain/marketplace.py` + `aitbc_shared/models/marketplace.py` | `status: str = "open"` — no enum, no transitions | Wire OfferFSM (A1) into offer lifecycle |
| **GPU service config** | `apps/gpu/src/gpu_service/main.py:280,298` | ❌ No Settings class, `chain_id` defaults to `""` (empty string), `BLOCKCHAIN_RPC_URL` defaults to 8202 (correct) | Add Settings class, fix chain_id default to `"ait-hub"` |
| **GPU service chain_id** | `apps/gpu/src/gpu_service/main.py:280` | `chain_id = transaction_data.get("chain_id") or os.getenv("CHAIN_ID", "")` — defaults to empty string | Default to `settings.default_chain_id` |
| **GPU offer model** | `apps/gpu/src/gpu_service/domain/gpu_marketplace.py:81-98` | `GPURegistry.status` = "available"/"booked"/"offline" — no FSM | Wire OfferFSM (A1) |
| **GPU tests** | `apps/gpu/tests/test_main.py` (46 lines) | Only 3 basic tests (health, status, profiles) | Add tests for chain_id, offer FSM, blockchain RPC |
| **Edge config** | `apps/edge/src/aitbc_edge/config.py:14-45` | ✅ Has Settings class (ServiceSettings subclass), `blockchain_rpc_port: 8202` (correct) | Add `MARKETPLACE_URL`, `AGENT_COORDINATOR_URL`, payment config |
| **Edge payment** | `apps/edge/src/aitbc_edge/routers/serve.py:27-33` | ❌ No payment verification before serving | Add payment verification (verify escrow on blockchain before serving) |
| **Edge GPU schema** | `apps/edge/src/aitbc_edge/schemas/gpu.py:11-36` vs `services/gpu_service.py:25-34` | ❌ **Schema mismatch**: schema has `listing_id`/`island_id`/`miner_id`/`gpu_type`, service code sets `gpu_id`/`model` — causes runtime errors | Fix schema to match service code, or fix service code to match schema |
| **Edge GPU fallback** | `apps/edge/src/aitbc_edge/services/gpu_service.py:54` | References `GPUListing.gpu_id` (nonexistent field) with `# type: ignore[attr-defined]` | Fix after schema fix |
| **Edge marketplace advertising** | — | ❌ No capability advertising to marketplace | Add edge node capability advertising (GPU models, capacity) |
| **Edge coordinator health** | — | ❌ No health reporting to agent-coordinator | Add heartbeat to agent-coordinator |
| **Edge ComputeResult schema** | `apps/edge/src/aitbc_edge/schemas/serve.py` vs `services/serve_service.py:111` | ❌ Schema has `result`, service references `output_data` | Fix schema mismatch |
| **Edge JWT config** | `apps/edge/src/aitbc_edge/config.py:38-40` | JWT settings defined but unused (dead code) | Either implement or remove (recommend: remove for now, add in v0.7.1) |
| **Blockchain GPU RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` | ✅ `/gpus`, `/gpu/register`, `/gpu/info/{gpu_id}`, `/gpu/allocate` — all chain_id-aware | No change needed (consume from marketplace/gpu/edge) |
| **Blockchain TransactionRequest** | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:21-32` | ✅ Accepts `chain_id` (optional), validates against supported chains | No change needed |
| **Blockchain GPURegistration** | `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py:10-33` | ✅ Has `chain_id`, `gpu_id`, `model`, `region`, `price_per_hour`, `status` | No change needed |
| **Blockchain GPUAllocation** | `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py:35-55` | ✅ Has `chain_id`, `allocation_id`, `gpu_id`, `client_id`, `status` | No change needed |
| **Shared HTTP client** | `aitbc/network/client.py:318-615` | ✅ `AsyncAITBCHTTPClient` with retry, circuit breaker, rate limiting | Base for new BlockchainRPCClient (A2) |
| **Shared config base** | `packages/aitbc-shared/aitbc_shared/core/config.py` | ✅ `ServiceSettings`, `DatabaseConfig` | Marketplace + GPU should subclass these |
| **Shared offer model** | `packages/aitbc-shared/aitbc_shared/models/marketplace.py` | `MarketplaceOffer.status = "open"` — no enum | Add OfferStatus enum (in aitbc/, not aitbc_shared) |

### Already Fixed (verified — no work needed)

1. ✅ **Marketplace direct SQLite** (v0.5.16 Bugs 17-18) — `marketplace_service.py:206-276` now uses RPC via httpx to `BLOCKCHAIN_RPC_URL/rpc/transactions`
2. ✅ **GPU service chain_id** — `main.py:280` includes `chain_id` in `blockchain_tx` dict (but defaults to empty string — B2 fixes the default)
3. ✅ **Blockchain GPU RPC** — `/gpus`, `/gpu/register`, `/gpu/info`, `/gpu/allocate` all accept and filter by `chain_id`
4. ✅ **TransactionRequest chain_id** — accepts and validates `chain_id`
5. ✅ **Edge config** — already uses `ServiceSettings` subclass with `blockchain_rpc_port: 8202`

---

## Architecture: Compute Marketplace with Chain Awareness

```
┌──────────────────────────────────────────────────────────────────────┐
│ Compute Marketplace (v0.6.6)                                         │
│                                                                      │
│  GPU Service (apps/gpu/)                                             │
│    POST /v1/transactions → blockchain /rpc/transaction               │
│    - chain_id = settings.default_chain_id (NEW — was "")            │
│    - GPU offer registered on blockchain (GPU_REGISTER tx)            │
│    - Offer status tracked via OfferFSM (A1)                          │
│                                                                      │
│  Marketplace Service (apps/marketplace/)                             │
│    GET /v1/marketplace/offers → blockchain /rpc/gpus?chain_id=X     │
│    - chain_id filter in RPC queries (NEW)                            │
│    - MatchingService → agent-coordinator /tasks/submit (NEW)        │
│    - Offer lifecycle via OfferFSM (A1)                               │
│                                                                      │
│  Edge Service (apps/edge/)                                           │
│    POST /v1/serve/requests → verify payment on blockchain (NEW)     │
│    - Edge advertises capabilities to marketplace (NEW)               │
│    - Edge reports health to agent-coordinator (NEW)                  │
│    - Schema mismatches fixed (NEW)                                   │
│                                                                      │
│  Shared Core (aitbc/)                                                │
│    OfferFSM (A1) — available → reserved → in_use → available/delist  │
│    BlockchainRPCClient (A2) — wraps AsyncAITBCHTTPClient             │
│      - query_offers(chain_id, model, region, ...)                    │
│      - submit_transaction(chain_id, tx_data)                         │
│      - verify_escrow(escrow_id)                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/marketplace/offer_fsm.py` (new), `aitbc/marketplace/blockchain_rpc.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/marketplace/`, `apps/gpu/`, `apps/edge/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/marketplace/` utilities. Agent B owns all `apps/marketplace/`, `apps/gpu/`, `apps/edge/` files. Agent B consumes Agent A's utilities. No shared files are touched by both agents.

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.6 — Compute Marketplace
