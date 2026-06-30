# v0.7.0 Cross-Chain Bridge Basics — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Cross-Chain Bridge Basics — Lock/Unlock, RPC, Simple Transfers, Monitoring

**Goal**: Complete the foundational cross-chain bridge infrastructure in blockchain-node. The core bridge logic already exists (`cross_chain/bridge.py` — 401 lines, lock/confirm flow, partial proof validation). This release adds the missing pieces: refund/unlock endpoint, bridge balance query, bridge health monitoring, CLI command fixes, batch operations, and a shared bridge client SDK in `aitbc/bridge/`.

> **Scope constraint**: This release targets bridge **basics** only — lock/unlock RPC, simple transfers, monitoring, CLI. It does NOT add multi-sig validation, time-locks, cross-chain signature verification (v0.7.1), or Merkle proof verification / proposer-set tracking / block header signatures (v0.7.2). The existing `BRIDGE_RELEASE_ENABLED=false` fence remains in place — the confirm/release path stays gated until v0.7.2 completes full cryptographic verification.

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) ✅, [v0.6.1](../v0.6.1/change.log) ✅, [v0.6.3](../v0.6.3/change.log) ✅, [v0.6.4](../v0.6.4/change.log) ✅, [v0.5.16](../v0.5.16/change.log) ✅. All technical prerequisites complete. v0.6.6/v0.6.7 (product track) are in progress but touch different code (marketplace/pool-hub) — no file conflicts with bridge work.

> **Risk**: Low-Medium. The bridge core already exists and is tested (401-line test suite). This release adds missing endpoints and monitoring — it does not change the proof validation logic. The `BRIDGE_RELEASE_ENABLED=false` fence prevents unauthorized fund release until v0.7.2.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (BridgeClient, bridge types, proof utilities, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (bridge config, RPC endpoints, CLI fixes, monitoring, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets)
- [Already Fixed / Exists](#already-fixed--exists-verified--no-work-needed)
- [Architecture](#architecture-bridge-basics-v070)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [BridgeClient + Bridge Types](./agent-a.md#a1-bridgeclient--bridge-types)
- [Proof Utilities](./agent-a.md#a2-proof-utilities)
- [Unit Tests](./agent-a.md#a3-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Bridge Config + Constants](./agent-b.md#b1-bridge-config--constants)
- [Missing RPC Endpoints](./agent-b.md#b2-missing-rpc-endpoints)
- [Fix CLI Bridge Commands](./agent-b.md#b3-fix-cli-bridge-commands)
- [Bridge Monitoring](./agent-b.md#b4-bridge-monitoring)
- [CLI Node Bridge Commands](./agent-b.md#b5-cli-node-bridge-commands)
- [Integration Tests](./agent-b.md#b6-integration-tests)
- [Verification](./agent-b.md#b7-verification)
- [Coordination Protocol](./agent-b.md#coordination-protocol)

---

## Status Baseline — Verified Code Targets (from subagent investigation, 2026-06-29)

| Component | Location | Current State | v0.7.0 Target |
|-----------|----------|---------------|---------------|
| **Bridge core** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` (401 lines) | ✅ EXISTS — `CrossChainBridge` with `initiate_transfer()`, `confirm_transfer()`, `get_transfer()`, `list_pending_transfers()`, `_validate_proof()` (partial), `_verify_proposer_signature()` (accepts any valid sig) | No change to proof logic. Add `refund_transfer()` method for unlock/cancel. |
| **BridgeStatus enum** | `cross_chain/bridge.py:27-36` | ✅ EXISTS — pending, locked, confirmed, completed, failed, refunded | No change needed |
| **BridgeTransfer dataclass** | `cross_chain/bridge.py:38-55` | ✅ EXISTS — transfer_id, source_chain, target_chain, sender, recipient, amount, asset, status, source/target_tx_hash, lock/confirm_time, proof | No change needed |
| **CrossChainTransfer table** | `base_models.py:193-211` | ✅ EXISTS — SQLModel with transfer_id PK, indexed source/target_chain, sender, recipient, status | No change needed |
| **Bridge RPC — lock** | `rpc/bridge.py:18-88` | ✅ EXISTS — `POST /bridge/lock` with signature validation (Bug 7 fix) | No change needed |
| **Bridge RPC — confirm** | `rpc/bridge.py:90-152` | ✅ EXISTS — `POST /bridge/confirm`, gated by `BRIDGE_RELEASE_ENABLED` | No change needed |
| **Bridge RPC — transfer status** | `rpc/bridge.py:154-186` | ✅ EXISTS — `GET /bridge/transfer/{transfer_id}` | Add `/bridge/status/{transfer_id}` alias |
| **Bridge RPC — pending** | `rpc/bridge.py:188-216` | ✅ EXISTS — `GET /bridge/pending?chain_id=` | No change needed |
| **Bridge RPC — unlock** | — | ❌ MISSING — no refund/cancel endpoint | Add `POST /bridge/unlock` for refunding pending transfers |
| **Bridge RPC — balance** | — | ❌ MISSING — no bridge balance query | Add `GET /bridge/balance/{chain_id}` |
| **Bridge RPC — health** | — | ❌ MISSING — no health check endpoint | Add `GET /bridge/health` |
| **Bridge RPC — batch** | — | ❌ MISSING — no batch operations | Add `POST /bridge/batch/lock`, `POST /bridge/batch/confirm` |
| **Bridge manager** | `network/bridge_manager.py` (270 lines) | ✅ EXISTS — island-to-island connection management (request/approve/establish/terminate), in-memory only | Add health monitoring, stuck transfer detection, metrics collection |
| **Bridge config** | `config.py:223,252,284-290` | ⚠️ PARTIAL — `bridge_islands`, `bridge_request_monitor_interval`, `bridge_release_enabled` only | Add `bridge_timeout`, `bridge_retry_limit`, `bridge_fee_basis_points`, `bridge_supported_chains`, `bridge_batch_size`, `bridge_monitor_interval` |
| **Bridge tests** | `tests/test_bridge_suite.py` (401 lines) | ✅ EXISTS — proof verification, lock/confirm endpoints, lifecycle, cross-chain contamination | Add tests for unlock, balance, health, batch, monitoring |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` (78 lines) | ❌ BROKEN — calls non-existent `/rpc/bridge/start`, `/status`, `/stop` endpoints. Falls back to simulated data. | Replace with actual endpoints: `bridge lock`, `bridge confirm`, `bridge unlock`, `bridge status`, `bridge pending`, `bridge balance`, `bridge health` |
| **CLI node bridge** | `cli/aitbc_cli/commands/node/bridge.py` (52 lines) | ❌ STUBS — `request`, `approve`, `reject`, `list-bridges` all return simulated data | Wire to actual `/islands/bridge` + bridge_manager RPC |
| **Bridge constants** | `aitbc/constants.py` | ❌ NONE — no bridge-specific constants | Add bridge constants (fee default, timeout default, retry limit) |
| **Shared bridge SDK** | — | ❌ NONE — no shared bridge client library | Create `aitbc/bridge/` package with BridgeClient, types, proof utilities |
| **Block header signatures** | `base_models.py:25-76` | ❌ NOT IMPLEMENTED — `proposer` field is address string, no signature field | DEFERRED to v0.7.1 (adds block signing) |
| **Proposer-set tracking** | — | ❌ NONE — `_verify_proposer_signature` accepts any valid signer | DEFERRED to v0.7.2 (full proposer-set verification) |
| **Merkle proof verification** | `state/merkle_patricia_trie.py:73-121` | ✅ EXISTS — `verify_proof(key, value, proof)` ready | DEFERRED to v0.7.2 (bridge uses it for state proofs) |
| **Signature utilities** | `aitbc/crypto/crypto.py` | ✅ EXISTS — `recover_signer()`, `verify_signature()` using secp256k1 | Reuse in bridge proof utilities (A2) |
| **bridge-monitor app** | `apps/bridge-monitor/` (574 lines) | ⚠️ UNRELATED — monitors Ethereum→AIT deposits, not AITBC cross-chain bridges | No change needed (separate concern) |
| **Coordinator-api cross-chain** | `apps/coordinator-api/src/app/contexts/cross_chain/` | ⚠️ SEPARATE — has own bridge models, no integration with blockchain-node bridge RPC | DEFERRED — v0.7.0 focuses on blockchain-node bridge only |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Bridge core exists** — `CrossChainBridge` with lock/confirm/transfer/pending flow (401 lines)
2. ✅ **CrossChainTransfer table exists** — SQLModel with proper indexes
3. ✅ **Bridge RPC lock endpoint** — `POST /bridge/lock` with signature validation
4. ✅ **Bridge RPC confirm endpoint** — `POST /bridge/confirm` with `BRIDGE_RELEASE_ENABLED` fence
5. ✅ **Bridge RPC transfer status** — `GET /bridge/transfer/{transfer_id}`
6. ✅ **Bridge RPC pending list** — `GET /bridge/pending?chain_id=`
7. ✅ **Bridge manager exists** — island-to-island connection management (270 lines)
8. ✅ **Bridge test suite exists** — 401 lines covering proof verification, endpoints, lifecycle
9. ✅ **Merkle Patricia Trie ready** — `verify_proof()` available for v0.7.2
10. ✅ **Signature utilities ready** — `recover_signer()`, `verify_signature()` in `aitbc/crypto/crypto.py`
11. ✅ **Bridge release fence** — `BRIDGE_RELEASE_ENABLED=false` prevents unauthorized minting

---

## Architecture: Bridge Basics (v0.7.0)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — NEW)                                    │
│                                                                      │
│  BridgeClient (A1) — HTTP client for bridge RPC:                     │
│    lock(), confirm(), unlock(), get_transfer(),                      │
│    list_pending(), get_balance(), health()                           │
│                                                                      │
│  Bridge types (A1) — BridgeStatus, BridgeTransfer,                   │
│    BridgeProof, BridgeConfig (shared dataclasses)                    │
│                                                                      │
│  Proof utilities (A2) — build_lock_proof(), validate_proof_fields()  │
│    using aitbc/crypto/crypto.py recover_signer()                     │
│    (basic validation only — NOT Merkle verification, deferred v0.7.2)│
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge lock            │    │                                      │
│  bridge confirm         │    │  RPC endpoints (B2):                 │
│  bridge unlock          │───▶│    POST /bridge/lock        ✅ exists │
│  bridge status          │    │    POST /bridge/confirm     ✅ exists │
│  bridge pending         │    │    POST /bridge/unlock      ❌ NEW    │
│  bridge balance         │    │    GET  /bridge/balance/{c} ❌ NEW    │
│  bridge health          │    │    GET  /bridge/health      ❌ NEW    │
│                         │    │    GET  /bridge/status/{id} ❌ alias  │
│  Uses BridgeClient (A1) │    │    POST /bridge/batch/lock  ❌ NEW    │
│  instead of raw HTTP    │    │    POST /bridge/batch/confirm❌ NEW   │
│                         │    │                                      │
│  Fix broken commands    │    │  Bridge config (B1):                 │
│  (currently calls       │    │    bridge_timeout, bridge_retry,     │
│   non-existent          │    │    bridge_fee, bridge_supported_     │
│   /rpc/bridge/start)    │    │    chains, bridge_batch_size,        │
│                         │    │    bridge_monitor_interval           │
│                         │    │                                      │
│                         │    │  Bridge monitoring (B4):             │
│                         │    │    health checks, stuck transfer     │
│                         │    │    detection, metrics                │
│                         │    │                                      │
│                         │    │  Tests (B6):                         │
│                         │    │    unlock, balance, health, batch,   │
│                         │    │    monitoring, CLI integration       │
└─────────────────────────┘    └──────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/bridge/__init__.py` (new), `aitbc/bridge/client.py` (new), `aitbc/bridge/types.py` (new), `aitbc/bridge/proof.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 7 items | `apps/blockchain-node/src/aitbc_chain/config.py`, `rpc/bridge.py`, `cross_chain/bridge.py`, `network/bridge_manager.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `cli/aitbc_cli/commands/node/bridge.py`, `aitbc/constants.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns new `aitbc/bridge/` package. Agent B owns all `apps/` and `cli/` files. Agent B consumes Agent A's `BridgeClient` and types. No shared files are touched by both agents. Agent B also owns `aitbc/constants.py` (bridge constants).

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.0 — Cross-Chain Bridge Basics
