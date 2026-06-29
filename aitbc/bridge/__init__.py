"""AITBC cross-chain bridge shared SDK (v0.7.0).

Provides:
- BridgeClient: async HTTP client for blockchain-node bridge RPC endpoints
- BridgeStatus: bridge transfer lifecycle status enum
- BridgeTransfer: cross-chain transfer record dataclass
- BridgeProof: lock proof dataclass (basic validation only; v0.7.2 adds Merkle)
- BridgeConfig: bridge client configuration
- build_lock_proof / validate_proof_fields / verify_proposer_signature:
  proof generation + basic validation utilities
- proof_to_dict / dict_to_proof: proof serialization helpers
- transfer_from_dict: parse a BridgeTransfer from an RPC response dict
"""

from __future__ import annotations

from .client import BridgeClient, transfer_from_dict
from .proof import (
    REQUIRED_PROOF_FIELDS,
    build_lock_proof,
    dict_to_proof,
    proof_to_dict,
    validate_proof_fields,
    verify_proposer_signature,
)
from .types import BridgeConfig, BridgeProof, BridgeStatus, BridgeTransfer

__all__ = [
    "REQUIRED_PROOF_FIELDS",
    "BridgeClient",
    "BridgeConfig",
    "BridgeProof",
    "BridgeStatus",
    "BridgeTransfer",
    "build_lock_proof",
    "dict_to_proof",
    "proof_to_dict",
    "transfer_from_dict",
    "validate_proof_fields",
    "verify_proposer_signature",
]
