# v0.9.0 Atomic Cross-Chain Settlement — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Atomic Cross-Chain Settlement — HTLC-based escrow, atomic release, timeout/refund, proof chaining, chaos testing.

**Goal**: Implement the full atomic settlement layer on top of the bridge security (v0.7.1), oracle verification (v0.7.2), and inter-chain trading (v0.8.0-v0.8.2) layers. Uses HTLCs (Hashed Timelock Contracts) — two-phase commit is dropped (see change.log §"HTLC vs Two-Phase Commit — DECISION: HTLC").

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) ✅, [v0.7.1](../v0.7.1/change.log) ✅, [v0.7.2](../v0.7.2/change.log) ✅, [v0.8.0](../v0.8.0/change.log) ✅, [v0.8.1](../v0.8.1/change.log) ✅, [v0.8.2](../v0.8.2/change.log) ✅. v0.7.4 (oracle fallback) ✅ Agent A. v0.7.5 (consensus) not required — single-validator PoA remains active.

> **Risk**: 🔴 HIGHEST. Atomic cross-chain settlement caused the largest hacks in crypto history (Wormhole $325M, Ronin $625M, Poly Network $611M). Requires dual external security audits + 6+ months testnet chaos testing before mainnet.

> **Not on the critical path for v1.0.0**: If security audit cannot be completed, v1.0.0 can ship with non-atomic settlement (manual admin refund) and defer atomic settlement to v1.1.0 (see suggestions.md line 14).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (settlement types, HTLC utilities, settlement client, proof chaining, trading types extension, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (escrow config, tables, settlement service, HTLC integration, RPC endpoints, trading endpoints, InterChainTrade model, coordinator, CLI, bridge confirm, chaos testing, integration tests)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Already Implemented](#already-implemented-reusable-no-work-needed)
- [Task Split Overview](#task-split-overview)
- [Coordination](#coordination)
- [Risk Mitigation](#risk-mitigation)
- [Fallback for v1.0.0](#fallback-for-v100)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [Settlement Types](./agent-a.md#a1-settlement-types)
- [HTLC Utilities](./agent-a.md#a2-htlc-utilities)
- [Settlement Client](./agent-a.md#a3-settlement-client)
- [Proof Chaining](./agent-a.md#a4-proof-chaining)
- [Extend Trading Types](./agent-a.md#a5-extend-trading-types)
- [Unit Tests](./agent-a.md#a6-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Escrow Config](./agent-b.md#b1-escrow-config)
- [Escrow Tables](./agent-b.md#b2-escrow-tables)
- [CrossChainSettlementService](./agent-b.md#b3-crosschainsettlementservice)
- [HTLC Contract Integration](./agent-b.md#b4-htlc-contract-integration)
- [Settlement RPC Endpoints](./agent-b.md#b5-settlement-rpc-endpoints)
- [Trading Service Settlement Endpoints](./agent-b.md#b6-trading-service-settlement-endpoints)
- [Extend InterChainTrade Model](./agent-b.md#b7-extend-interchain-trade-model)
- [Atomic Settlement Coordinator](./agent-b.md#b8-atomic-settlement-coordinator)
- [CLI Commands](./agent-b.md#b9-cli-commands)
- [Enable Bridge Confirm Path](./agent-b.md#b10-enable-bridge-confirm-path)
- [Chaos Testing Infrastructure](./agent-b.md#b11-chaos-testing-infrastructure)
- [Integration Tests](./agent-b.md#b12-integration-tests)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.9.0 Target |
|-----------|----------|---------------|---------------|
| **HTLC smart contract** | `contracts/contracts/CrossChainAtomicSwap.sol` (145 lines) | ✅ COMPLETE — `initiateSwap()`, `completeSwap()`, `refundSwap()` with hashlock/timelock | Integrate with Python SDK |
| **HTLC Python execution** | `apps/coordinator-api/src/app/contexts/cross_chain/services/cross_chain/bridge_enhanced.py:471-535` | ⚠️ STUB — generates fake addresses via SHA256, no real contract calls | Replace stub with real HTLC coordination |
| **Cross-chain escrow types** | — | ❌ NONE — no CrossChainEscrow or EscrowProof types | Create in `aitbc/settlement/` (Agent A) |
| **HTLC utilities** | — | ❌ NONE — no secret generation, hashlock, timelock utilities in shared SDK | Create in `aitbc/settlement/htlc.py` (Agent A) |
| **Settlement client** | — | ❌ NONE — no SettlementClient for atomic settlement RPC | Create in `aitbc/settlement/client.py` (Agent A) |
| **PaymentEscrow** | `aitbc/crypto/payment_escrow.py` (238 lines) | ✅ COMPLETE but single-chain only — no HTLC, no cross-chain fields | Reference for design, don't extend (new module) |
| **Bridge SDK** | `aitbc/bridge/` | ✅ COMPLETE (v0.7.0-v0.7.2) — BridgeClient, BridgeProof, proof verification, oracle | Settlement layer builds on top |
| **Trading SDK** | `aitbc/trading/` | ✅ COMPLETE (v0.8.0-v0.8.2) — InterChainTradeData, TradingBridgeClient, offer sync | Settlement extends trade lifecycle |
| **InterChainTradeStatus** | `aitbc/trading/types.py:20-41` | ✅ DEFINED — has LOCKED, CONFIRMED, COMPLETED states (not yet used) | Wire settlement to these states |
| **InterChainTrade model** | `apps/trading/src/trading_service/domain/inter_chain.py:42-43` | ⚠️ PLACEHOLDERS — `source_tx_hash`, `dest_tx_hash` are None, commented "set in v0.9.0" | Populate with settlement tx hashes |
| **TradingBridgeClient** | `aitbc/trading/bridge.py:77-104` | ⚠️ PARTIAL — `lock_escrow()` exists, no settle/refund/HTLC methods | Add settlement methods |
| **Bridge confirm path** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py:163-220` | ⚠️ GATED — `BRIDGE_RELEASE_ENABLED=false` due to partial proof verification | Enable after v0.7.2 verification is wired |
| **Bridge RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` (650 lines) | ✅ 17 endpoints — lock, confirm, unlock, batch, validators, security, block-headers, oracle | Add settlement-specific endpoints |
| **CLI trade commands** | `cli/aitbc_cli/commands/trade.py` (316 lines) | ✅ v0.8.0-v0.8.2 commands exist | Add `trade lock-escrow`, `trade settle` |
| **Chaos testing** | `tests/harness/multi_node.py` | ⚠️ PARTIAL — partition/Byzantine simulation exists for consensus, not settlement | Add settlement-specific chaos scenarios |
| **EscrowManager** | `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` (553 lines) | ✅ COMPLETE — marketplace job escrow (not cross-chain) | Reference for design, separate module |

### Already Implemented (reusable, no work needed)

1. ✅ **HTLC smart contract** (`CrossChainAtomicSwap.sol`) — `initiateSwap()`, `completeSwap()`, `refundSwap()` with SHA256 hashlock, timelock, ReentrancyGuard
2. ✅ **Bridge SDK** (`aitbc/bridge/`) — BridgeClient (15 RPC methods), BridgeProof, proof verification (v0.7.2), oracle fallback (v0.7.4)
3. ✅ **Trading SDK** (`aitbc/trading/`) — InterChainTradeData, InterChainTradeStatus (with LOCKED/CONFIRMED states), TradingBridgeClient.lock_escrow()
4. ✅ **PaymentEscrow** (`aitbc/crypto/payment_escrow.py`) — single-chain escrow with lock/release/refund/expire (reference design)
5. ✅ **Multi-node test harness** (`tests/harness/multi_node.py`) — partition/Byzantine simulation infrastructure
6. ✅ **Bridge refund** (`apps/blockchain-node/.../bridge.py:248-312`) — `refund_transfer()` for bridge transfers
7. ✅ **InterChainTradeStatus** — LOCKED, CONFIRMED, COMPLETED states already in enum

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 6 items | `aitbc/settlement/` (new package), `aitbc/trading/` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 12 items | `apps/blockchain-node/`, `apps/trading/`, `apps/coordinator-api/`, `cli/`, `tests/` |

**Conflict boundary**: Agent A owns `aitbc/settlement/` (new) and `aitbc/trading/` (extend types/client). Agent B owns `apps/`, `cli/`, `contracts/`, `tests/harness/`. Agent B consumes Agent A's settlement types and client.

**Sequencing**: Agent A goes first (shared settlement SDK). Agent B starts after Agent A A1-A3 complete (types + HTLC utilities + client needed for service integration).

---

## Coordination

### Shared Files

Agent A owns `aitbc/settlement/` (new) and `aitbc/trading/types.py` (extend). Agent B owns `apps/`, `cli/`, `contracts/`, `tests/harness/`. No file conflicts.

Agent B imports from Agent A's modules:
- `from aitbc.settlement import CrossChainEscrow, EscrowProof, SettlementConfig, EscrowStatus, HTLCState, ProofType`
- `from aitbc.settlement.htlc import generate_secret, compute_hashlock, verify_secret, calculate_source_timelock, calculate_dest_timelock, validate_timelocks, HTLCStateMachine`
- `from aitbc.settlement.client import SettlementClient`
- `from aitbc.settlement.proofs import build_lock_proof, build_execution_proof, build_release_proof, build_settlement_proof, verify_proof_chain`
- `from aitbc.trading import SettlementPhase`

### Sequencing

1. **Phase 1** (Agent A): A1 (types), A2 (HTLC utils), A3 (client) — foundation
2. **Phase 2** (parallel): Agent A A4 (proofs), A5 (trading types), Agent B B1 (config), B2 (tables), B7 (InterChainTrade model)
3. **Phase 3** (Agent B): B3 (settlement service — needs A1+A2), B4 (HTLC integration — needs A2), B5 (RPC endpoints — needs A3), B10 (bridge confirm — independent)
4. **Phase 4** (Agent B): B6 (trading endpoints — needs B5), B8 (coordinator — needs B3), B9 (CLI — needs A3+B5)
5. **Phase 5** (parallel): Agent A A6 (unit tests), Agent B B11 (chaos harness), B12 (integration tests)
6. **Phase 6** (operational): Security audit, testnet soak test, mainnet activation

### Activation Gating

Settlement is gated behind `escrow_enabled = false` in config until all of the following are met:

- [ ] Agent A A1-A6 complete (settlement SDK + tests)
- [ ] Agent B B1-B12 complete (all service code + tests)
- [ ] Bridge confirm path secured (B10 — v0.7.2 proof verification wired)
- [ ] All integration tests pass (B12)
- [ ] All chaos tests pass (B11 — no partial state under any failure)
- [ ] External security audit #1 passed (bridge security firm)
- [ ] External security audit #2 passed (cross-chain settlement firm)
- [ ] Testnet deployment + 6+ month soak test
- [ ] No funds stuck in any test scenario
- [ ] Rollback plan documented (set `escrow_enabled = false` to disable)

### Rollback Plan

If issues are found post-activation:
1. Set `escrow_enabled = false` in config
2. Restart blockchain-node — new escrows rejected, existing escrows allowed to complete or timeout/refund
3. Manual refund for any stuck escrows (admin tool)
4. Investigate and fix issues
5. Re-run security audit + testnet soak before re-activating

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Funds stuck in escrow (partial state) | HTLC timeout ensures automatic refund; chaos tests verify no stuck funds |
| Secret leaked before settlement | Secret only generated by buyer, revealed only on source chain after dest execution |
| Timelock race (timeout during release) | Dest timelock < source timelock (margin); validate_timelocks() enforces this |
| Bridge proof forgery | v0.7.2 in-process verification (Merkle + proposer sig + finality); oracle fallback (v0.7.4) |
| Chain reorg invalidates lock proof | Proofs anchored to finalized blocks (finality_config); reorg simulation in chaos tests |
| Oracle provides incorrect verification | Oracle fallback policy (v0.7.4); oracle failure simulation in chaos tests |
| Byzantine validator signs invalid state | Multi-sig threshold (v0.7.1); Byzantine simulation in chaos tests |
| HTLC contract vulnerability | External security audit; OpenZeppelin ReentrancyGuard; tested on testnet first |
| Network partition mid-settlement | Timeout triggers refund on both chains; partition simulation in chaos tests |

### Fallback for v1.0.0

If security audit cannot be completed or chaos testing reveals unfixable issues:
- v1.0.0 ships with `escrow_enabled = false`
- Non-atomic settlement: manual admin refund for stuck trades
- Atomic settlement deferred to v1.1.0
- This does not block v1.0.0 — single-chain trading and bridge transfers work without escrow

---

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.9.0 — Atomic Cross-Chain Settlement
