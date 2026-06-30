"""AITBC atomic cross-chain settlement shared SDK (v0.9.0).

Provides HTLC-based atomic settlement types, utilities, and client for
cross-chain trades between AITBC blockchain networks (islands).

Components:
- EscrowStatus: enum for escrow lifecycle (pending → locked → verified →
  executing → completed, with refunded/failed/disputed branches)
- HTLCState: enum for single-chain HTLC state (created → funded →
  completed/refunded)
- ProofType: enum for proof chain types (lock, verification, execution,
  release, settlement)
- CrossChainEscrow: cross-chain escrow record dataclass
- EscrowProof: single proof in the settlement proof chain
- SettlementConfig: settlement client + service configuration
- generate_secret / compute_hashlock / verify_secret: HTLC secret utilities
- calculate_source_timelock / calculate_dest_timelock / validate_timelocks:
  timelock calculation and validation
- HTLCStateMachine: HTLC lifecycle state machine
- build_lock_proof / build_verification_proof / build_execution_proof /
  build_release_proof / build_settlement_proof: proof chain builders
- verify_proof_chain: proof chain integrity verification
- proof_to_dict / dict_to_proof: proof serialization
- SettlementClient: async HTTP client for settlement RPC endpoints

The settlement layer builds on:
- Bridge SDK (v0.7.0-v0.7.2): lock/confirm/unlock, proof verification
- Trading SDK (v0.8.0-v0.8.2): inter-chain trade lifecycle
- HTLC smart contract (CrossChainAtomicSwap.sol): on-chain HTLC execution
"""

from __future__ import annotations

from .client import SettlementClient
from .htlc import (
    HTLCStateMachine,
    calculate_dest_timelock,
    calculate_source_timelock,
    compute_hashlock,
    generate_secret,
    validate_timelocks,
    verify_secret,
)
from .proofs import (
    build_execution_proof,
    build_lock_proof,
    build_release_proof,
    build_settlement_proof,
    build_verification_proof,
    compute_proof_hash,
    dict_to_proof,
    proof_to_dict,
    verify_proof_chain,
)
from .types import (
    CrossChainEscrow,
    EscrowProof,
    EscrowStatus,
    HTLCState,
    ProofType,
    SettlementConfig,
)

__all__ = [
    "CrossChainEscrow",
    "EscrowProof",
    "EscrowStatus",
    "HTLCState",
    "HTLCStateMachine",
    "ProofType",
    "SettlementClient",
    "SettlementConfig",
    "build_execution_proof",
    "build_lock_proof",
    "build_release_proof",
    "build_settlement_proof",
    "build_verification_proof",
    "calculate_dest_timelock",
    "calculate_source_timelock",
    "compute_hashlock",
    "compute_proof_hash",
    "dict_to_proof",
    "generate_secret",
    "proof_to_dict",
    "validate_timelocks",
    "verify_proof_chain",
    "verify_secret",
]
