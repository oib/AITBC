"""Compatibility SDK for retired native cross-chain settlement.

Use SettlementClient to look up historical escrow status and proof chains.
Native HTLC settlement writes are retired (#2385); legacy write wrappers
still target routes that return HTTP 410. The public HTLC helpers from
aitbc.settlement.htlc are deprecated for new integrations but remain
importable for compatibility.
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
