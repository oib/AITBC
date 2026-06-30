# v0.9.0 Atomic Cross-Chain Settlement — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create the `aitbc/settlement/` package with HTLC utilities, cross-chain escrow types, proof chaining, settlement config, and a SettlementClient. Extend the trading SDK with settlement-related types.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.8.0 Agent A ✅, v0.8.2 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/settlement/ aitbc/trading/ && ./venv/bin/python -m ruff check aitbc/settlement/ aitbc/trading/ tests/unit/test_settlement_sdk.py && ./venv/bin/python -m pytest tests/unit/test_settlement_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/settlement/types.py` — EscrowStatus, SettlementStatus, HTLCState, CrossChainEscrow, EscrowProof, SettlementConfig, ProofChain types | 🔴 P0 | `aitbc/settlement/types.py` (new), `aitbc/settlement/__init__.py` (new) | ✅ |
| A2 | Create `aitbc/settlement/htlc.py` — secret generation, hashlock computation, timelock calculation, HTLC state machine | 🔴 P0 | `aitbc/settlement/htlc.py` (new) | ✅ |
| A3 | Create `aitbc/settlement/client.py` — SettlementClient async HTTP client for settlement RPC endpoints | 🔴 P0 | `aitbc/settlement/client.py` (new) | ✅ |
| A4 | Create `aitbc/settlement/proofs.py` — proof chaining utilities (lock proof → execution proof → release proof → settlement proof) | High | `aitbc/settlement/proofs.py` (new) | ✅ |
| A5 | Extend `aitbc/trading/types.py` — add settlement fields to InterChainTradeData, add SettlementPhase enum | High | `aitbc/trading/types.py` (extend), `aitbc/trading/__init__.py` (extend) | ✅ |
| A6 | Unit tests for A1-A5 | High | `tests/unit/test_settlement_sdk.py` (new) | ✅ |

---

## A1: Settlement Types

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

---

## A2: HTLC Utilities

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

---

## A3: Settlement Client

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

---

## A4: Proof Chaining

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

---

## A5: Extend Trading Types

Extend `aitbc/trading/types.py`:
- Add `SettlementPhase` enum: `NONE`, `ESCROW_CREATED`, `ESCROW_LOCKED`, `LOCK_VERIFIED`, `TRADE_EXECUTED`, `SETTLED`, `REFUNDED`, `DISPUTED`
- Add settlement fields to `InterChainTradeData`:
  - `escrow_id: str = ""`
  - `settlement_phase: str = "none"`  # SettlementPhase value
  - `secret_hash: str = ""`
  - `source_timelock: int = 0`
  - `dest_timelock: int = 0`
- Export `SettlementPhase` from `aitbc/trading/__init__.py`

---

## A6: Unit Tests

`tests/unit/test_settlement_sdk.py` — tests for:
- HTLC: secret generation (32 bytes, unique), hashlock computation, secret verification, timelock calculation (source > dest), timelock validation, state machine transitions
- Types: CrossChainEscrow defaults, EscrowProof fields, SettlementConfig defaults, EscrowStatus/HTLCState/ProofType enums
- Proof chaining: proof hash computation, chain building, chain verification (valid, broken link, wrong order, non-increasing heights)
- SettlementClient: mocked httpx for all RPC methods
- Trading types: SettlementPhase enum, InterChainTradeData with settlement fields

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.9.0 — Atomic Cross-Chain Settlement
**Agent**: Agent A (Shared Core)
