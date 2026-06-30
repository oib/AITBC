"""AITBC cross-chain bridge shared SDK (v0.7.0, v0.7.1, v0.7.2).

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

v0.7.1 additions:
- ValidatorInfo / ValidatorSet: bridge validator set types
- ThresholdProof: M-of-N multi-sig proof dataclass
- ValidatorSetRegistry: in-memory validator set lookup with epoch tracking
- verify_threshold_signatures / recover_all_signers / check_threshold:
  threshold signature verification utilities

v0.7.2 additions:
- BridgeBlockHeader / FinalityConfig / ProofVerificationResult: verification types
- VerificationMode: in_process | oracle enum
- OracleClient / InProcessVerifier / ExternalOracleClient: oracle interface
- MerkleProofVerifier: protocol for Merkle proof verification
- validate_block_header / check_finality / build_verification_message:
  block header validation + finality checking utilities
"""

from __future__ import annotations

from .client import BridgeClient, transfer_from_dict
from .multisig import (
    check_threshold,
    recover_all_signers,
    verify_threshold_signatures,
)
from .oracle import (
    ExternalOracleClient,
    InProcessVerifier,
    MerkleProofVerifier,
    OracleClient,
    OracleFallbackPolicy,
)
from .proof import (
    REQUIRED_PROOF_FIELDS,
    build_lock_proof,
    dict_to_proof,
    proof_to_dict,
    validate_proof_fields,
    verify_proposer_signature,
)
from .types import (
    BridgeBlockHeader,
    BridgeConfig,
    BridgeProof,
    BridgeStatus,
    BridgeTransfer,
    FinalityConfig,
    ProofVerificationResult,
    ThresholdProof,
    ValidatorInfo,
    ValidatorSet,
    VerificationMode,
)
from .validators import ValidatorSetRegistry
from .verification import (
    build_verification_message,
    check_finality,
    validate_block_header,
)

__all__ = [
    "BridgeBlockHeader",
    "BridgeClient",
    "BridgeConfig",
    "BridgeProof",
    "BridgeStatus",
    "BridgeTransfer",
    "ExternalOracleClient",
    "FinalityConfig",
    "InProcessVerifier",
    "MerkleProofVerifier",
    "OracleClient",
    "OracleFallbackPolicy",
    "ProofVerificationResult",
    "REQUIRED_PROOF_FIELDS",
    "ThresholdProof",
    "ValidatorInfo",
    "ValidatorSet",
    "ValidatorSetRegistry",
    "VerificationMode",
    "build_lock_proof",
    "build_verification_message",
    "check_finality",
    "check_threshold",
    "dict_to_proof",
    "proof_to_dict",
    "recover_all_signers",
    "transfer_from_dict",
    "validate_block_header",
    "validate_proof_fields",
    "verify_proposer_signature",
    "verify_threshold_signatures",
]
