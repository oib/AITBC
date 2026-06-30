# v0.9.0 — Agent Task Assignment

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
- [Status Baseline](./overview.md#status-baseline--verified-code-targets-2026-06-29)
- [Already Implemented](./overview.md#already-implemented-reusable-no-work-needed)
- [Task Split Overview](./overview.md#task-split-overview)
- [Coordination](./overview.md#coordination)
- [Risk Mitigation](./overview.md#risk-mitigation)
- [Fallback for v1.0.0](./overview.md#fallback-for-v100)

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

## Agent A — Shared Core

**Scope**: Create the `aitbc/settlement/` package with HTLC utilities, cross-chain escrow types, proof chaining, settlement config, and a SettlementClient. Extend the trading SDK with settlement-related types.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.8.0 Agent A ✅, v0.8.2 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/settlement/ aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/settlement/ aitbc/trading/ tests/unit/test_settlement_sdk.py && ./venv/bin/python -m pytest tests/unit/test_settlement_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/settlement/types.py` — EscrowStatus, SettlementStatus, HTLCState, CrossChainEscrow, EscrowProof, SettlementConfig, ProofChain types | 🔴 P0 | `aitbc/settlement/types.py` (new), `aitbc/settlement/__init__.py` (new) | ✅ |
| A2 | Create `aitbc/settlement/htlc.py` — secret generation, hashlock computation, timelock calculation, HTLC state machine | 🔴 P0 | `aitbc/settlement/htlc.py` (new) | ✅ |
| A3 | Create `aitbc/settlement/client.py` — SettlementClient async HTTP client for settlement RPC endpoints | 🔴 P0 | `aitbc/settlement/client.py` (new) | ✅ |
| A4 | Create `aitbc/settlement/proofs.py` — proof chaining utilities (lock proof → execution proof → release proof → settlement proof) | High | `aitbc/settlement/proofs.py` (new) | ✅ |
| A5 | Extend `aitbc/trading/types.py` — add settlement fields to InterChainTradeData, add SettlementPhase enum | High | `aitbc/trading/types.py` (extend), `aitbc/trading/__init__.py` (extend) | ✅ |
| A6 | Unit tests for A1-A5 | High | `tests/unit/test_settlement_sdk.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Settlement Types

Create `aitbc/settlement/types.py`:

```python
class EscrowStatus(StrEnum):
    PENDING = "pending"       # escrow created, not yet locked
    LOCKED = "locked"         # funds locked on source chain
    VERIFIED = "verified"     # lock proof verified on destination chain
    EXECUTING = "executing"   # trade execution in progress
    COMPLETED = "completed"   # both chains settled
    REFUNDED = "refunded"     # both chains refunded (timeout)
    FAILED = "failed"         # settlement failed (dispute/error)
    DISPUTED = "disputed"     # under dispute resolution

class HTLCState(StrEnum):
    CREATED = "created"       # HTLC contract created
    FUNDED = "funded"         # funds locked in HTLC
    COMPLETED = "completed"   # secret revealed, funds claimed
    REFUNDED = "refunded"     # timelock expired, funds refunded
    EXPIRED = "expired"       # timelock expired, not yet refunded

class ProofType(StrEnum):
    LOCK = "lock"             # proof that escrow is locked on source chain
    VERIFICATION = "verification"  # proof that destination verified the lock
    EXECUTION = "execution"   # proof that trade was executed on destination
    RELEASE = "release"       # proof that escrow was released on destination
    SETTLEMENT = "settlement"  # proof that source released after verifying release

@dataclass
class CrossChainEscrow:
    """Cross-chain escrow record for atomic settlement."""
    escrow_id: str
    trade_id: str
    source_chain: str
    dest_chain: str
    sender: str          # buyer (locks funds)
    recipient: str       # seller (claims funds)
    amount: int
    asset: str = "native"
    status: EscrowStatus = EscrowStatus.PENDING
    # HTLC fields
    secret_hash: str = ""         # SHA256 hash of secret
    secret: str = ""              # revealed secret (empty until revealed)
    source_timelock: int = 0      # source chain timelock (block height or timestamp)
    dest_timelock: int = 0        # destination chain timelock (must be < source)
    # Proof fields
    lock_proof: dict[str, Any] = field(default_factory=dict)
    execution_proof: dict[str, Any] = field(default_factory=dict)
    release_proof: dict[str, Any] = field(default_factory=dict)
    # Transaction hashes
    source_lock_tx_hash: str = ""
    dest_execution_tx_hash: str = ""
    source_release_tx_hash: str = ""
    dest_release_tx_hash: str = ""
    # Timestamps
    created_at: float = 0.0
    locked_at: float = 0.0
    settled_at: float = 0.0
    refunded_at: float = 0.0
    # Timeout
    timeout_seconds: int = 3600   # default 1 hour
    timeout_extended: bool = False

@dataclass
class EscrowProof:
    """A single proof in the settlement proof chain."""
    proof_type: ProofType
    chain_id: str
    block_height: int
    block_hash: str
    tx_hash: str
    proposer_signature: str = ""
    validator_signatures: list[str] = field(default_factory=list)
    merkle_proof: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    # Link to previous proof in chain
    previous_proof_hash: str = ""

@dataclass
class SettlementConfig:
    """Configuration for atomic cross-chain settlement."""
    enabled: bool = False
    htlc_enabled: bool = True
    default_timeout_seconds: int = 3600      # 1 hour
    large_trade_timeout_seconds: int = 86400  # 24 hours for large trades
    max_timeout_extension_seconds: int = 604800  # 7 days max extension
    source_timelock_margin_blocks: int = 10  # extra blocks for source timelock
    dest_timelock_margin_blocks: int = 20   # extra blocks for dest (must be < source)
    require_proof_verification: bool = True
    require_multisig: bool = True
    settlement_rpc_url: str = "http://localhost:8202"  # blockchain node
    trading_rpc_url: str = "http://localhost:8104"     # trading service
    timeout: int = 30  # HTTP client timeout
```

Create `aitbc/settlement/__init__.py` exporting all types.

#### A2: HTLC Utilities

Create `aitbc/settlement/htlc.py`:

```python
def generate_secret() -> str:
    """Generate a cryptographically random 32-byte secret (hex)."""

def compute_hashlock(secret: str) -> str:
    """Compute SHA256 hash of the secret (the hashlock)."""

def verify_secret(secret: str, hashlock: str) -> bool:
    """Verify that a secret matches a hashlock."""

def calculate_source_timelock(
    current_block_height: int,
    timeout_seconds: int,
    block_time_seconds: int,
    margin_blocks: int = 10,
) -> int:
    """Calculate source chain timelock (block height).

    Formula: current_height + (timeout_seconds / block_time_seconds) + margin_blocks
    The source timelock must be LATER than the destination timelock to give
    the buyer time to claim after the seller reveals the secret.
    """

def calculate_dest_timelock(
    source_timelock: int,
    source_block_time: int,
    dest_block_time: int,
    margin_blocks: int = 20,
) -> int:
    """Calculate destination chain timelock (block height).

    The dest timelock must be EARLIER than the source timelock (converted
    to dest chain time) so that:
    1. Seller must reveal secret on dest chain before dest timelock
    2. Buyer has time to use secret on source chain before source timelock

    Formula: source_timelock * (dest_block_time / source_block_time) - margin_blocks
    """

def validate_timelocks(
    source_timelock: int,
    dest_timelock: int,
    source_current_height: int,
    dest_current_height: int,
) -> list[str]:
    """Validate that timelocks are safe for atomic settlement.

    Returns list of error strings (empty if valid).
    Checks:
    1. Source timelock is in the future
    2. Dest timelock is in the future
    3. Dest timelock expires before source timelock (when converted to same time base)
    4. Sufficient margin between dest and source timelock
    """

class HTLCStateMachine:
    """State machine for HTLC lifecycle management."""

    def __init__(self) -> None:
        self._transitions = {
            HTLCState.CREATED: {HTLCState.FUNDED, HTLCState.EXPIRED},
            HTLCState.FUNDED: {HTLCState.COMPLETED, HTLCState.REFUNDED, HTLCState.EXPIRED},
            HTLCState.COMPLETED: set(),  # terminal
            HTLCState.REFUNDED: set(),   # terminal
            HTLCState.EXPIRED: {HTLCState.REFUNDED},
        }

    def can_transition(self, from_state: HTLCState, to_state: HTLCState) -> bool: ...
    def transition(self, from_state: HTLCState, to_state: HTLCState) -> HTLCState: ...
    def is_terminal(self, state: HTLCState) -> bool: ...
```

#### A3: Settlement Client

Create `aitbc/settlement/client.py`:

```python
class SettlementClient:
    """Async HTTP client for atomic cross-chain settlement RPC endpoints.

    Wraps the blockchain node's settlement endpoints (added by Agent B B5)
    and the trading service's settlement endpoints (Agent B B6).
    """

    def __init__(self, config: SettlementConfig | None = None) -> None: ...

    # Escrow operations
    async def create_escrow(self, trade_id, source_chain, dest_chain, sender, recipient, amount, timeout_seconds=None) -> dict: ...
    async def lock_escrow(self, escrow_id) -> dict: ...
    async def verify_lock(self, escrow_id) -> dict: ...
    async def execute_trade(self, escrow_id) -> dict: ...
    async def settle(self, escrow_id, secret) -> dict: ...
    async def refund(self, escrow_id) -> dict: ...
    async def get_escrow(self, escrow_id) -> dict: ...
    async def get_escrow_status(self, escrow_id) -> str: ...

    # Timeout management
    async def extend_timeout(self, escrow_id, extension_seconds) -> dict: ...
    async def check_timeout(self, escrow_id) -> dict: ...

    # Proof operations
    async def get_lock_proof(self, escrow_id) -> dict: ...
    async def get_execution_proof(self, escrow_id) -> dict: ...
    async def get_release_proof(self, escrow_id) -> dict: ...
    async def get_settlement_proof(self, escrow_id) -> dict: ...
    async def verify_proof_chain(self, escrow_id) -> dict: ...

    # Dispute resolution
    async def file_dispute(self, escrow_id, reason, evidence) -> dict: ...
    async def resolve_dispute(self, escrow_id, resolution) -> dict: ...
```

Follow the pattern of `GovernanceClient` (async httpx, context manager, `raise_for_status()`).

#### A4: Proof Chaining

Create `aitbc/settlement/proofs.py`:

```python
def compute_proof_hash(proof: EscrowProof) -> str:
    """Compute SHA256 hash of a proof (for chaining)."""

def build_lock_proof(
    source_chain, lock_tx_hash, amount, sender, recipient,
    block_height, block_hash, proposer_signature,
    validator_signatures=None, merkle_proof=None,
) -> EscrowProof: ...

def build_execution_proof(
    dest_chain, execution_tx_hash, trade_id,
    block_height, block_hash, proposer_signature,
    previous_proof_hash,
) -> EscrowProof: ...

def build_release_proof(
    dest_chain, release_tx_hash, escrow_id,
    block_height, block_hash, proposer_signature,
    previous_proof_hash,
) -> EscrowProof: ...

def build_settlement_proof(
    source_chain, settlement_tx_hash, escrow_id,
    block_height, block_hash, proposer_signature,
    previous_proof_hash,
) -> EscrowProof: ...

def verify_proof_chain(proofs: list[EscrowProof]) -> list[str]:
    """Verify that a chain of proofs is valid.

    Checks:
    1. Each proof's previous_proof_hash matches the hash of the preceding proof
    2. Proof types are in correct order (lock → verification → execution → release → settlement)
    3. Each proof's block height is greater than the previous proof's block height
    Returns list of error strings (empty if valid).
    """

def proof_to_dict(proof: EscrowProof) -> dict[str, Any]: ...
def dict_to_proof(data: dict[str, Any]) -> EscrowProof: ...
```

#### A5: Extend Trading Types

Extend `aitbc/trading/types.py`:
- Add `SettlementPhase` enum: `NONE`, `ESCROW_CREATED`, `ESCROW_LOCKED`, `LOCK_VERIFIED`, `TRADE_EXECUTED`, `SETTLED`, `REFUNDED`, `DISPUTED`
- Add settlement fields to `InterChainTradeData`:
  - `escrow_id: str = ""`
  - `settlement_phase: str = "none"`  # SettlementPhase value
  - `secret_hash: str = ""`
  - `source_timelock: int = 0`
  - `dest_timelock: int = 0`
- Export `SettlementPhase` from `aitbc/trading/__init__.py`

#### A6: Unit Tests

`tests/unit/test_settlement_sdk.py` — tests for:
- HTLC: secret generation (32 bytes, unique), hashlock computation, secret verification, timelock calculation (source > dest), timelock validation, state machine transitions
- Types: CrossChainEscrow defaults, EscrowProof fields, SettlementConfig defaults, EscrowStatus/HTLCState/ProofType enums
- Proof chaining: proof hash computation, chain building, chain verification (valid, broken link, wrong order, non-increasing heights)
- SettlementClient: mocked httpx for all RPC methods
- Trading types: SettlementPhase enum, InterChainTradeData with settlement fields

---

## Agent B — Apps & Infrastructure

**Scope**: Implement cross-chain escrow tables, wire HTLC contract integration, add settlement RPC endpoints, implement atomic settlement coordination, add CLI commands, create chaos testing infrastructure, and integration tests.

**Working directory**: `/opt/aitbc/apps/`, `/opt/aitbc/cli/`, `/opt/aitbc/contracts/`, `/opt/aitbc/tests/`

**Prerequisite**: Agent A A1-A3 complete (settlement types + HTLC utilities + client). v0.8.2 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/cross_chain/ apps/trading/src/trading_service/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/blockchain-node/src:apps/trading/src:aitbc ./venv/bin/python -m pytest apps/blockchain-node/tests/test_settlement.py tests/integration/test_atomic_settlement.py -q -o addopts="" --timeout=30
```

### Tasks

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

### Agent B — Detailed Instructions

#### B1: Escrow Config

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

#### B2: Escrow Tables

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

#### B3: CrossChainSettlementService

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

#### B4: HTLC Contract Integration

Replace the stub `_execute_htlc_swap()` / `_create_htlc_contract()` / `_complete_htlc()` in `bridge_enhanced.py` with real contract interaction:
- Use Agent A's `generate_secret()` / `compute_hashlock()` for HTLC parameters
- Call the deployed `CrossChainAtomicSwap.sol` contract via web3.py or the blockchain node's contract execution RPC
- `initiate_swap()` → calls contract `initiateSwap(hashlock, timelock)`
- `complete_swap()` → calls contract `completeSwap(swapId, secret)`
- `refund_swap()` → calls contract `refundSwap(swapId)`
- Store contract swap IDs and states in the CrossChainEscrowRecord

#### B5: Settlement RPC Endpoints

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

#### B6: Trading Service Settlement Endpoints

Add to `apps/trading/src/trading_service/main.py`:
- `POST /v1/trading/trades/{id}/lock-escrow` — initiate escrow lock for a trade
- `POST /v1/trading/trades/{id}/settle` — settle a trade
- `GET /v1/trading/trades/{id}/settlement-status` — get settlement status

These wrap the blockchain-node settlement RPC (Agent B B5) via Agent A's `SettlementClient`.

#### B7: Extend InterChainTrade Model

Add to `apps/trading/src/trading_service/domain/inter_chain.py`:
- `escrow_id: str | None = None`
- `settlement_phase: str = "none"`  # SettlementPhase value
- `secret_hash: str = ""`
- `source_timelock: int = 0`
- `dest_timelock: int = 0`

Add Alembic migration for new columns.

#### B8: Atomic Settlement Coordinator

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

#### B9: CLI Commands

Add to `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade lock-escrow --trade-id <id> [--timeout <seconds>]` — lock escrow for a trade
- `aitbc trade settle --trade-id <id> --secret <secret>` — settle a trade
- `aitbc trade settlement-status --trade-id <id>` — get settlement status
- `aitbc trade refund --trade-id <id>` — trigger refund (if timeout reached)

Uses Agent A's `SettlementClient` (A3) to call settlement RPC endpoints.

#### B10: Enable Bridge Confirm Path

Wire v0.7.2 proof verification into `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py:confirm_transfer()`:
- Replace the trivial `_validate_proof()` (lines 244-257) with real verification using `InProcessVerifier` from `aitbc.bridge.oracle`
- Verify proposer signature, Merkle proof, and finality
- Remove the `BRIDGE_RELEASE_ENABLED` gate (set to True by default)
- Keep backward compatibility for legacy blocks (empty signature → skip)

This is a prerequisite for atomic settlement — the confirm path must be secure before settlement can release funds.

#### B11: Chaos Testing Infrastructure

Create `tests/harness/settlement_chaos.py`:
- `SettlementChaosHarness` — extends MultiNodeHarness with settlement-specific scenarios:
  - `simulate_partition_during_lock()` — partition source/dest mid-lock
  - `simulate_partition_during_settle()` — partition mid-settle
  - `simulate_reorg_during_lock()` — reorg source chain after lock
  - `simulate_timeout_race()` — timeout reached during release phase
  - `simulate_byzantine_validator()` — validator signs invalid bridge state
  - `simulate_oracle_failure()` — oracle provides incorrect lock verification
- Each scenario verifies: atomicity maintained, no funds stuck, correct final state

#### B12: Integration Tests

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

### Dependencies

```
v0.7.2 (bridge verification) ✅     v0.8.0 (trading SDK) ✅     v0.8.2 (offer sync) ✅
    │                                     │                         │
    ├── A1 (settlement types) ────┐       │                         │
    ├── A2 (HTLC utilities) ─────┤       │                         │
    ├── A3 (settlement client) ───┤       │                         │
    ├── A4 (proof chaining) ──────┤       │                         │
    ├── A5 (trading types ext) ───┤───────┘                         │
    │                              ├── A6 (unit tests)              │
    │                              │                                │
    ├── B1 (config) ───────────────┐│                                │
    ├── B2 (escrow tables) ────────┤├── needs A1                     │
    ├── B3 (settlement service) ───┤├── needs A1+A2                  │
    ├── B4 (HTLC integration) ─────┤├── needs A2                     │
    ├── B5 (settlement RPC) ───────┤├── needs A3                     │
    ├── B6 (trading endpoints) ────┤├── needs B5+A3                  │
    ├── B7 (InterChainTrade ext) ──┤├── needs A5                     │
    ├── B8 (coordinator) ──────────┤├── needs B3+B4                  │
    ├── B9 (CLI) ──────────────────┤├── needs A3+B5                  │
    ├── B10 (bridge confirm) ──────┤│  independent                   │
    ├── B11 (chaos harness) ───────┤├── needs B8                     │
    └── B12 (integration tests) ───┘│  needs B3+B8+A4                │
                                   │
    Phase 6: Security audit ───────┘  needs all code complete
```

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

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.9.0 — Atomic Cross-Chain Settlement
