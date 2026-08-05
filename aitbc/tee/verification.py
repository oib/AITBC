"""ZK + TEE dual-verification policy (v0.14.2 §A1).

Provides ``VerificationMode``, ``ZKProof``, ``DualVerificationPolicy``, and
helpers to evaluate ZK-only, TEE-only, or combined verification. Real
enforcement still needs a ZK verifier and a platform-specific quote validator;
the in-memory policy here is a selectable policy skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .attestation import AttestationQuote, AttestationVerifier
from .errors import TEEError


class VerificationMode(StrEnum):
    """Supported verification modes."""

    ZK_ONLY = "zk_only"
    TEE_ONLY = "tee_only"
    BOTH = "both"


@dataclass
class ZKProof:
    """Zero-knowledge proof placeholder with optional Ed25519 signature binding.

    When ``verifying_key``, ``public_inputs``, and ``proof_data`` are supplied,
    ``verify()`` performs an Ed25519 signature check as a simulator for a real
    ZK verifier. Otherwise it falls back to the ``verified`` boolean.
    """

    proof_id: str
    # Fail closed. A proof constructed without a verifying key and proof_data must not
    # assert its own validity; verify() falls back to this flag, so defaulting it True
    # made an unverified proof indistinguishable from a checked one.
    verified: bool = False
    context_id: str = ""
    verifying_key: bytes = b""
    public_inputs: bytes = b""
    proof_data: bytes = b""
    meta: dict[str, Any] = field(default_factory=dict)

    def _bound_inputs(self) -> bytes:
        if self.context_id:
            return self.context_id.encode() + b"|" + self.public_inputs
        return self.public_inputs

    def verify(self) -> bool:
        """Verify the proof.

        If a verifying key is present, verify the Ed25519 signature over the
        (context-bound) public inputs; otherwise trust ``self.verified``.
        """
        if not self.verifying_key or not self.proof_data:
            return self.verified
        try:
            pub = Ed25519PublicKey.from_public_bytes(self.verifying_key)
            pub.verify(self.proof_data, self._bound_inputs())
            return True
        except InvalidSignature:
            return False


@dataclass
class DualVerificationResult:
    """Detailed result of a dual-verification policy check."""

    verified: bool
    mode: VerificationMode
    tee_ok: bool
    zk_ok: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DualVerificationPolicy:
    """Policy that selects ZK-only, TEE-only, or combined verification."""

    mode: VerificationMode
    allowed_measurements: set[str] | frozenset[str] | None = None

    def _verify_tee(self, quote: AttestationQuote | None) -> bool:
        if quote is None:
            return False
        return AttestationVerifier(self.allowed_measurements).verify(quote)

    def _verify_zk(self, zk_proof: ZKProof | None) -> bool:
        return zk_proof is not None and zk_proof.verify()

    def verify(self, quote: AttestationQuote | None, zk_proof: ZKProof | None) -> bool:
        """Evaluate the verification policy for the given evidence."""
        return self.verify_with_result(quote, zk_proof).verified

    def verify_with_result(
        self,
        quote: AttestationQuote | None,
        zk_proof: ZKProof | None,
    ) -> DualVerificationResult:
        """Evaluate the policy and return a detailed result."""
        tee_ok = self._verify_tee(quote)
        zk_ok = self._verify_zk(zk_proof)

        if self.mode == VerificationMode.ZK_ONLY:
            if zk_proof is None:
                raise TEEError("ZK proof required for zk_only mode")
            verified = zk_ok
        elif self.mode == VerificationMode.TEE_ONLY:
            if quote is None:
                raise TEEError("TEE quote required for tee_only mode")
            verified = tee_ok
        elif self.mode == VerificationMode.BOTH:
            verified = tee_ok and zk_ok
        else:
            raise ValueError(f"unsupported verification mode {self.mode}")

        return DualVerificationResult(
            verified=verified,
            mode=self.mode,
            tee_ok=tee_ok,
            zk_ok=zk_ok,
        )


def verify_with_policy(
    policy: DualVerificationPolicy,
    quote: AttestationQuote | None,
    zk_proof: ZKProof | None,
) -> bool:
    """Top-level helper to verify evidence against a dual-verification policy."""
    return policy.verify(quote, zk_proof)


def verify_with_result(
    policy: DualVerificationPolicy,
    quote: AttestationQuote | None,
    zk_proof: ZKProof | None,
) -> DualVerificationResult:
    """Top-level helper returning a detailed verification result."""
    return policy.verify_with_result(quote, zk_proof)
