# v0.9.0 Atomic Cross-Chain Settlement — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Implement cross-chain escrow tables, wire HTLC contract integration, add settlement RPC endpoints, implement atomic settlement coordination, add CLI commands, create chaos testing infrastructure, and integration tests.

**Working directory**: `/opt/aitbc/apps/`, `/opt/aitbc/cli/`, `/opt/aitbc/contracts/`, `/opt/aitbc/tests/`

**Prerequisite**: Agent A A1-A3 complete (settlement types + HTLC utilities + client). v0.8.2 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/cross_chain/ apps/trading/src/trading_service/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/blockchain-node/src:apps/trading/src:aitbc ./venv/bin/python -m pytest apps/blockchain-node/tests/test_settlement.py tests/integration/test_atomic_settlement.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add escrow config to blockchain-node Settings | Medium | `apps/blockchain-node/src/aitbc_chain/config.py` (extend) | ✅ |
| B2 | Add CrossChainEscrow + EscrowProof SQLModel tables | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py` (extend) | ✅ |
| B3 | Implement CrossChainSettlementService — escrow lifecycle, HTLC coordination, timeout monitoring | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py` (new) | ✅ |
| B4 | Integrate HTLC contract calls — replace bridge_enhanced.py stubs with real contract interaction | 🔴 P0 | `apps/coordinator-api/src/app/contexts/cross_chain/services/cross_chain/bridge_enhanced.py` (rewrite HTLC section) | ✅ |
| B5 | Add settlement RPC endpoints to blockchain-node | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` (extend), `apps/blockchain-node/src/aitbc_chain/rpc/router.py` (extend) | ✅ |
| B6 | Add settlement endpoints to trading service | High | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B7 | Extend InterChainTrade model with settlement fields | High | `apps/trading/src/trading_service/domain/inter_chain.py` (extend) | ✅ |
| B8 | Implement atomic settlement coordinator — orchestrates lock → verify → execute → settle (or refund) | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement_coordinator.py` (new) | ✅ |
| B9 | Add CLI commands — `trade lock-escrow`, `trade settle`, `trade settlement-status` | Medium | `cli/aitbc_cli/commands/trade.py` (extend) | ✅ |
| B10 | Enable bridge confirm path — wire v0.7.2 proof verification, remove `BRIDGE_RELEASE_ENABLED` gate | High | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` (extend) | ✅ |
| B11 | Chaos testing infrastructure — settlement-specific partition/reorg/timeout/Byzantine/oracle scenarios | High | `tests/harness/settlement_chaos.py` (new), `tests/integration/test_atomic_settlement.py` (new) | ✅ |
| B12 | Integration tests — full settlement lifecycle, timeout/refund, proof chain verification, multi-node | 🔴 P0 | `apps/blockchain-node/tests/test_settlement.py` (new), `tests/integration/test_atomic_settlement.py` (extend) | ✅ |

---

## B1: Escrow Config

Add to `apps/blockchain-node/src/aitbc_chain/config.py`:
```python
# Cross-chain settlement (v0.9.0)
escrow_enabled: bool = False
escrow_atomic_settlement: bool = True
escrow_timeout_default: int = 3600  # 1 hour
escrow_timeout_large: int = 86400  # 24 hours for large trades
escrow_timeout_extension_max: int = 604800  # 7 days max extension
escrow_htlc_enabled: bool = True
escrow_htlc_contract_address: str = ""  # deployed CrossChainAtomicSwap.sol address
escrow_require_proof_verification: bool = True
escrow_large_trade_threshold: int = 10000  # trades above this use large timeout
```

---

## B2: Escrow Tables

Add to `apps/blockchain-node/src/aitbc_chain/base_models.py`:
```python
class CrossChainEscrowRecord(SQLModel, table=True):
    """Cross-chain escrow record for atomic settlement (v0.9.0)."""
    __tablename__ = "cross_chain_escrows"
    __table_args__ = (
        UniqueConstraint("escrow_id", name="uix_escrow_id"),
        Index("ix_escrow_trade_id", "trade_id"),
        Index("ix_escrow_status", "status"),
        {"extend_existing": True},
    )
    id: int | None = Field(default=None, primary_key=True)
    escrow_id: str = Field(index=True)
    trade_id: str = Field(index=True)
    source_chain: str = Field(index=True)
    dest_chain: str
    sender: str
    recipient: str
    amount: int
    asset: str = "native"
    status: str = "pending"  # EscrowStatus value
    secret_hash: str = ""
    secret: str = ""
    source_timelock: int = 0
    dest_timelock: int = 0
    source_lock_tx_hash: str = ""
    dest_execution_tx_hash: str = ""
    source_release_tx_hash: str = ""
    dest_release_tx_hash: str = ""
    timeout_seconds: int = 3600
    timeout_extended: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    locked_at: datetime | None = None
    settled_at: datetime | None = None
    refunded_at: datetime | None = None

class EscrowProofRecord(SQLModel, table=True):
    """Proof record in the settlement proof chain (v0.9.0)."""
    __tablename__ = "escrow_proofs"
    __table_args__ = (
        Index("ix_proof_escrow_id", "escrow_id"),
        Index("ix_proof_type", "proof_type"),
        {"extend_existing": True},
    )
    id: int | None = Field(default=None, primary_key=True)
    escrow_id: str = Field(index=True)
    proof_type: str  # ProofType value
    chain_id: str
    block_height: int
    block_hash: str
    tx_hash: str
    proposer_signature: str = ""
    validator_signatures_json: str = "[]"
    merkle_proof_json: str = "[]"
    previous_proof_hash: str = ""
    timestamp: float = 0.0
```

Add Alembic migration under `apps/blockchain-node/alembic/versions/` (if exists) or document manual migration.

---

## B3: CrossChainSettlementService

Create `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py`:

This is the core settlement service that orchestrates the escrow lifecycle:
- `create_escrow()` — create escrow record, generate HTLC secret/hashlock, calculate timelocks
- `lock_escrow()` — call bridge `lock()` on source chain, store lock proof
- `verify_lock()` — verify lock proof on destination chain via oracle (v0.7.2)
- `execute_trade()` — execute trade on destination chain, store execution proof
- `settle()` — reveal secret on source chain, release escrow, store settlement proof
- `refund()` — refund escrow on both chains after timeout
- `check_timeouts()` — monitor all pending escrows for timeout, trigger refund
- `extend_timeout()` — extend timeout with mutual agreement (multi-sig)
- `get_escrow()` / `get_escrow_status()` — query escrow state
- `get_proof_chain()` — return all proofs for an escrow

Uses Agent A's `aitbc.settlement.htlc` for HTLC utilities, `aitbc.settlement.proofs` for proof chaining, and `aitbc.bridge` for bridge operations.

---

## B4: HTLC Contract Integration

Replace the stub `_execute_htlc_swap()` / `_create_htlc_contract()` / `_complete_htlc()` in `bridge_enhanced.py` with real contract interaction:
- Use Agent A's `generate_secret()` / `compute_hashlock()` for HTLC parameters
- Call the deployed `CrossChainAtomicSwap.sol` contract via web3.py or the blockchain node's contract execution RPC
- `initiate_swap()` → calls contract `initiateSwap(hashlock, timelock)`
- `complete_swap()` → calls contract `completeSwap(swapId, secret)`
- `refund_swap()` → calls contract `refundSwap(swapId)`
- Store contract swap IDs and states in the CrossChainEscrowRecord

---

## B5: Settlement RPC Endpoints

Add to `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`:
- `POST /bridge/settlement/create` — create escrow
- `POST /bridge/settlement/{id}/lock` — lock escrow
- `POST /bridge/settlement/{id}/verify` — verify lock proof
- `POST /bridge/settlement/{id}/execute` — execute trade
- `POST /bridge/settlement/{id}/settle` — settle (reveal secret)
- `POST /bridge/settlement/{id}/refund` — refund
- `GET /bridge/settlement/{id}` — get escrow status
- `POST /bridge/settlement/{id}/extend-timeout` — extend timeout
- `GET /bridge/settlement/{id}/proofs` — get proof chain
- `POST /bridge/settlement/{id}/dispute` — file dispute
- `POST /bridge/settlement/{id}/resolve` — resolve dispute

Register routes in `rpc/router.py`.

---

## B6: Trading Service Settlement Endpoints

Add to `apps/trading/src/trading_service/main.py`:
- `POST /v1/trading/trades/{id}/lock-escrow` — initiate escrow lock for a trade
- `POST /v1/trading/trades/{id}/settle` — settle a trade
- `GET /v1/trading/trades/{id}/settlement-status` — get settlement status

These wrap the blockchain-node settlement RPC (Agent B B5) via Agent A's `SettlementClient`.

---

## B7: Extend InterChainTrade Model

Add to `apps/trading/src/trading_service/domain/inter_chain.py`:
- `escrow_id: str | None = None`
- `settlement_phase: str = "none"`  # SettlementPhase value
- `secret_hash: str = ""`
- `source_timelock: int = 0`
- `dest_timelock: int = 0`

Add Alembic migration for new columns.

---

## B8: Atomic Settlement Coordinator

Create `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement_coordinator.py`:

This is the orchestrator that runs the full settlement lifecycle:
```
1. create_escrow(trade_id, ...) → escrow_id
2. lock_escrow(escrow_id) → source chain locked, lock proof generated
3. verify_lock(escrow_id) → destination chain verifies lock proof via oracle
4. execute_trade(escrow_id) → trade executed on destination, execution proof
5. settle(escrow_id, secret) → secret revealed, both chains settle atomically
   OR
5. refund(escrow_id) → timeout reached, both chains refund atomically
```

The coordinator handles:
- **Happy path**: lock → verify → execute → settle (both chains)
- **Timeout path**: lock → verify → timeout → refund (both chains)
- **Failure path**: lock → verify fails → refund source chain only
- **Dispute path**: any → dispute → resolution (manual or automated)

Runs as a background asyncio task that monitors pending escrows and advances them through the lifecycle.

---

## B9: CLI Commands

Add to `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade lock-escrow --trade-id <id> [--timeout <seconds>]` — lock escrow for a trade
- `aitbc trade settle --trade-id <id> --secret <secret>` — settle a trade
- `aitbc trade settlement-status --trade-id <id>` — get settlement status
- `aitbc trade refund --trade-id <id>` — trigger refund (if timeout reached)

Uses Agent A's `SettlementClient` (A3) to call settlement RPC endpoints.

---

## B10: Enable Bridge Confirm Path

Wire v0.7.2 proof verification into `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py:confirm_transfer()`:
- Replace the trivial `_validate_proof()` (lines 244-257) with real verification using `InProcessVerifier` from `aitbc.bridge.oracle`
- Verify proposer signature, Merkle proof, and finality
- Remove the `BRIDGE_RELEASE_ENABLED` gate (set to True by default)
- Keep backward compatibility for legacy blocks (empty signature → skip)

This is a prerequisite for atomic settlement — the confirm path must be secure before settlement can release funds.

---

## B11: Chaos Testing Infrastructure

Create `tests/harness/settlement_chaos.py`:
- `SettlementChaosHarness` — extends MultiNodeHarness with settlement-specific scenarios:
  - `simulate_partition_during_lock()` — partition source/dest mid-lock
  - `simulate_partition_during_settle()` — partition mid-settle
  - `simulate_reorg_during_lock()` — reorg source chain after lock
  - `simulate_timeout_race()` — timeout reached during release phase
  - `simulate_byzantine_validator()` — validator signs invalid bridge state
  - `simulate_oracle_failure()` — oracle provides incorrect lock verification
- Each scenario verifies: atomicity maintained, no funds stuck, correct final state

---

## B12: Integration Tests

Create `apps/blockchain-node/tests/test_settlement.py`:
- `test_create_escrow` — escrow record created with correct HTLC params
- `test_lock_escrow` — funds locked on source chain, lock proof generated
- `test_verify_lock` — lock proof verified on destination chain
- `test_settle_happy_path` — full lock → verify → execute → settle
- `test_refund_timeout` — lock → timeout → refund on both chains
- `test_refund_verify_fail` — lock → verify fails → refund source only
- `test_proof_chain_complete` — all 5 proofs generated and verified
- `test_proof_chain_broken_link` — broken chain detected
- `test_extend_timeout` — timeout extended with mutual agreement
- `test_htlc_secret_verification` — secret matches hashlock
- `test_timelock_validation` — invalid timelocks rejected

Create `tests/integration/test_atomic_settlement.py`:
- `test_full_settlement_lifecycle` — end-to-end with 2 blockchain nodes
- `test_settlement_under_partition` — partition mid-settle, verify refund
- `test_settlement_under_reorg` — reorg after lock, verify cancel
- `test_settlement_timeout_race` — timeout during release, verify atomicity
- `test_multi_node_settlement` — 3+ nodes, 1 Byzantine, settlement succeeds
- `test_no_funds_stuck` — verify no partial state under any failure

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.9.0 — Atomic Cross-Chain Settlement
**Agent**: Agent B (Apps & Infrastructure)
