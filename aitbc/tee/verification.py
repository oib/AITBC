"""ZK + TEE dual-verification policy (v0.14.2 §A1).

ponytail: This is a policy skeleton. Real enforcement needs a ZK verifier and
a TEE quote validator wired to a platform attestation service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .attestation import AttestationQuote, AttestationVerifier
from .errors import TEEError


class VerificationMode(StrEnum):
    """Supported verification modes."""

    ZK_ONLY = "zk_only"
    TEE_ONLY = "tee_only"
    BOTH = "both"


class ZKProof:
    """Placeholder for a zero-knowledge proof object."""

    def __init__(self, proof_id: str, verified: bool = True):
        self.proof_id = proof_id
        self.verified = verified


@dataclass
class DualVerificationPolicy:
    """Policy that selects ZK-only, TEE-only, or combined verification."""

    mode: VerificationMode
    allowed_measurements: set[str] | frozenset[str] | None = None

    def verify(self, quote: AttestationQuote | None, zk_proof: ZKProof | None) -> bool:
        """Evaluate the verification policy for the given evidence."""
        if self.mode == VerificationMode.ZK_ONLY:
            if zk_proof is None:
                raise TEEError("ZK proof required for zk_only mode")
            return zk_proof.verified
        if self.mode == VerificationMode.TEE_ONLY:
            if quote is None:
                raise TEEError("TEE quote required for tee_only mode")
            return AttestationVerifier(self.allowed_measurements).verify(quote)
        if self.mode == VerificationMode.BOTH:
            zk_ok = zk_proof is not None and zk_proof.verified
            tee_ok = quote is not None and AttestationVerifier(self.allowed_measurements).verify(quote)
            return zk_ok and tee_ok
        raise ValueError(f"unsupported verification mode {self.mode}")


def verify_with_policy(
    policy: DualVerificationPolicy,
    quote: AttestationQuote | None,
    zk_proof: ZKProof | None,
) -> bool:
    """Top-level helper to verify evidence against a dual-verification policy."""
    return policy.verify(quote, zk_proof)
