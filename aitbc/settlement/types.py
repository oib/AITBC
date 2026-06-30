"""Shared atomic cross-chain settlement types (v0.9.0 §A1).

These are the canonical shared SDK types for HTLC-based atomic cross-chain
settlement between AITBC blockchain networks (islands). They define the
escrow lifecycle, HTLC state, proof chain structure, and settlement
configuration used by the settlement service (Agent B B3) and CLI.

The settlement layer builds on top of:
- Bridge SDK (``aitbc.bridge``) — lock/confirm/unlock, proof verification
- Trading SDK (``aitbc.trading``) — inter-chain trade lifecycle
- HTLC smart contract (``contracts/contracts/CrossChainAtomicSwap.sol``)

Design rationale: HTLC (Hashed Timelock Contract) is chosen over
two-phase commit because HTLC has existing partial implementation, is
the industry standard for cross-chain atomic swaps, and has a simpler
failure model (timeout-based refund vs distributed abort coordination).
See ``docs/releases/v0.9.0/change.log`` §"HTLC vs Two-Phase Commit".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EscrowStatus(StrEnum):
    """Status of a cross-chain escrow for atomic settlement.

    The lifecycle is:
    pending → locked → verified → executing → completed
    Any state can transition to refunded (timeout) or failed (error).
    disputed can be entered from locked/verified/executing.

    - ``pending``: escrow created, not yet locked on source chain
    - ``locked``: funds locked on source chain (HTLC initiated)
    - ``verified``: lock proof verified on destination chain
    - ``executing``: trade execution in progress on destination chain
    - ``completed``: both chains settled atomically
    - ``refunded``: both chains refunded (timeout reached)
    - ``failed``: settlement failed (error or dispute resolution)
    - ``disputed``: under dispute resolution
    """

    PENDING = "pending"
    LOCKED = "locked"
    VERIFIED = "verified"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"
    DISPUTED = "disputed"


class HTLCState(StrEnum):
    """State of an HTLC (Hashed Timelock Contract) on a single chain.

    - ``created``: HTLC contract created but not yet funded
    - ``funded``: funds locked in HTLC (waiting for secret reveal or timeout)
    - ``completed``: secret revealed, funds claimed by participant
    - ``refunded``: timelock expired, funds returned to initiator
    - ``expired``: timelock expired, not yet refunded
    """

    CREATED = "created"
    FUNDED = "funded"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class ProofType(StrEnum):
    """Type of a proof in the settlement proof chain.

    The proof chain is: lock → verification → execution → release → settlement.
    Each proof links to the previous one via ``previous_proof_hash``.

    - ``lock``: proof that escrow is locked on source chain
    - ``verification``: proof that destination chain verified the lock
    - ``execution``: proof that trade was executed on destination chain
    - ``release``: proof that escrow was released on destination chain
    - ``settlement``: proof that source chain released after verifying release
    """

    LOCK = "lock"
    VERIFICATION = "verification"
    EXECUTION = "execution"
    RELEASE = "release"
    SETTLEMENT = "settlement"


@dataclass
class CrossChainEscrow:
    """Cross-chain escrow record for atomic settlement.

    This dataclass mirrors the fields stored in the blockchain node's
    ``CrossChainEscrowRecord`` SQLModel (Agent B B2) but is dependency-free
    for use by the CLI and other services.

    The escrow coordinates funds between two chains using HTLC:
    1. Buyer (sender) locks funds on source chain with a hashlock
    2. Seller (recipient) verifies lock and executes trade on dest chain
    3. Seller reveals secret on dest chain to claim funds
    4. Buyer uses revealed secret to claim on source chain
    5. If timeout reached, both chains refund
    """

    escrow_id: str
    trade_id: str
    source_chain: str
    dest_chain: str
    sender: str  # buyer (locks funds on source)
    recipient: str  # seller (claims funds on dest)
    amount: int
    asset: str = "native"
    status: EscrowStatus = EscrowStatus.PENDING

    # HTLC fields
    secret_hash: str = ""  # SHA256 hash of secret (the hashlock)
    secret: str = ""  # revealed secret (empty until revealed)
    source_timelock: int = 0  # source chain timelock (block height)
    dest_timelock: int = 0  # destination chain timelock (must be < source)

    # Proof fields (stored as dicts, structured via EscrowProof)
    lock_proof: dict[str, Any] = field(default_factory=dict)
    execution_proof: dict[str, Any] = field(default_factory=dict)
    release_proof: dict[str, Any] = field(default_factory=dict)

    # Transaction hashes
    source_lock_tx_hash: str = ""
    dest_execution_tx_hash: str = ""
    source_release_tx_hash: str = ""
    dest_release_tx_hash: str = ""

    # Timestamps (Unix epoch seconds)
    created_at: float = 0.0
    locked_at: float = 0.0
    settled_at: float = 0.0
    refunded_at: float = 0.0

    # Timeout configuration
    timeout_seconds: int = 3600  # default 1 hour
    timeout_extended: bool = False


@dataclass
class EscrowProof:
    """A single proof in the settlement proof chain.

    Each proof anchors a settlement event to a specific block on a chain.
    Proofs are chained: each proof's ``previous_proof_hash`` is the SHA256
    hash of the preceding proof, creating a tamper-evident chain.

    The full proof chain for a successful settlement is:
    1. Lock proof (source chain) — funds locked
    2. Verification proof (dest chain) — lock verified
    3. Execution proof (dest chain) — trade executed
    4. Release proof (dest chain) — funds released on dest
    5. Settlement proof (source chain) — funds released on source
    """

    proof_type: ProofType
    chain_id: str
    block_height: int
    block_hash: str
    tx_hash: str
    proposer_signature: str = ""
    validator_signatures: list[str] = field(default_factory=list)
    merkle_proof: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    # Link to previous proof in chain (SHA256 hash of preceding proof)
    previous_proof_hash: str = ""


@dataclass
class SettlementConfig:
    """Configuration for atomic cross-chain settlement.

    The settlement RPC endpoints are served by the blockchain node
    (port 8202, same as bridge RPC). The trading service settlement
    endpoints run on port 8104.

    Timelock margins ensure the destination timelock expires before the
    source timelock, giving the buyer time to claim on the source chain
    after the seller reveals the secret on the destination chain.
    """

    enabled: bool = False
    htlc_enabled: bool = True
    default_timeout_seconds: int = 3600  # 1 hour
    large_trade_timeout_seconds: int = 86400  # 24 hours for large trades
    max_timeout_extension_seconds: int = 604800  # 7 days max extension
    source_timelock_margin_blocks: int = 10  # extra blocks for source timelock
    dest_timelock_margin_blocks: int = 20  # extra blocks for dest (must be < source)
    require_proof_verification: bool = True
    require_multisig: bool = True
    settlement_rpc_url: str = "http://localhost:8202"  # blockchain node
    trading_rpc_url: str = "http://localhost:8104"  # trading service
    timeout: int = 30  # HTTP client timeout
