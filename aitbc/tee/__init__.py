"""AITBC TEE (Trusted Execution Environment) shared primitives (v0.14.1).

Provides attestation, enclave lifecycle, identity, sealed storage, and
confidential messaging types consumed by the coordinator-api attestation
service and agent runtime.
"""

from __future__ import annotations

from .attestation import (
    AttestationQuote,
    AttestationStatus,
    AttestationVerifier,
    QuoteGenerator,
    computation_transcript,
    load_or_create_signing_key,
    public_key_for_signing_key,
    verify_quote,
)
from .benchmark import TEEBenchmark, TEEBenchmarkResult
from .channel import ChannelState, TEEChannel, ChannelMessage
from .enclave import Enclave, EnclaveConfig, EnclaveStatus
from .errors import TEEError
from .identity import EnclaveIdentity, KeyProvisioningPolicy, SealedKeyBundle
from .sealed_storage import SealedBlob, seal, unseal
from .session import SessionState, TEESession
from .verification import (
    DualVerificationPolicy,
    DualVerificationResult,
    VerificationMode,
    ZKProof,
    verify_with_policy,
    verify_with_result,
)

__all__ = [
    "AttestationQuote",
    "AttestationStatus",
    "AttestationVerifier",
    "computation_transcript",
    "ChannelState",
    "DualVerificationPolicy",
    "DualVerificationResult",
    "Enclave",
    "EnclaveConfig",
    "EnclaveIdentity",
    "EnclaveStatus",
    "KeyProvisioningPolicy",
    "QuoteGenerator",
    "SealedBlob",
    "SealedKeyBundle",
    "TEEBenchmark",
    "TEEBenchmarkResult",
    "TEEChannel",
    "TEEError",
    "ChannelMessage",
    "TEESession",
    "SessionState",
    "VerificationMode",
    "ZKProof",
    "load_or_create_signing_key",
    "public_key_for_signing_key",
    "seal",
    "unseal",
    "verify_quote",
    "verify_with_policy",
    "verify_with_result",
]
