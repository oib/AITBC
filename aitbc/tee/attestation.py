"""TEE attestation quote generation/validation skeleton (v0.14.1 §A1).

Real quote handling requires platform-specific libraries (Intel SGX/V2, TDX,
AMD SEV, etc.). The Ed25519 signing layer here is a simulator-friendly
stand-in for a quote signed inside the enclave and verified by the platform
attestation service.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class AttestationStatus(StrEnum):
    """Status of an attestation quote."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass
class AttestationQuote:
    """Container for a TEE attestation quote."""

    quote_id: str = ""
    enclave_id: str = ""
    quote_blob: bytes = b""
    measurement: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=1))
    status: AttestationStatus = AttestationStatus.VALID
    signature: bytes = b""
    public_key: bytes = b""
    meta: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the quote has expired."""
        if now is None:
            now = datetime.now(UTC)
        if self.status == AttestationStatus.EXPIRED:
            return True
        return self.expires_at <= now

    def _signing_payload(self) -> bytes:
        return (
            self.quote_id.encode()
            + b"|"
            + self.enclave_id.encode()
            + b"|"
            + self.measurement.encode()
            + b"|"
            + self.quote_blob
            + b"|"
            + self.timestamp.isoformat().encode()
            + b"|"
            + self.expires_at.isoformat().encode()
        )

    def sign(self, signing_key: bytes) -> None:
        """Sign the quote with an Ed25519 key derived from ``signing_key``."""
        seed = hashlib.sha256(signing_key).digest()
        private_key = Ed25519PrivateKey.from_private_bytes(seed)
        self.public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.signature = private_key.sign(self._signing_payload())

    def verify_signature(self) -> bool:
        """Return True if the quote's signature is valid."""
        if not self.signature or not self.public_key:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(self.public_key)
            pub.verify(self.signature, self._signing_payload())
            return True
        except InvalidSignature:
            return False


class QuoteGenerator:
    """Generate local attestation quotes for an enclave."""

    def __init__(self, enclave_id: str = "", signing_key: bytes = b"") -> None:
        self.enclave_id = enclave_id
        self.signing_key = signing_key

    def generate(
        self,
        quote_id: str = "",
        enclave_id: str = "",
        measurement: str = "",
        report_data: bytes = b"",
    ) -> AttestationQuote:
        """Return a quote, optionally signed by the enclave.

        Supports both ``generate(quote_id, enclave_id, measurement)`` and
        ``generate(report_data=..., measurement=...)`` call patterns.
        """
        target_enclave = enclave_id or self.enclave_id
        if report_data:
            blob = report_data
        elif quote_id:
            blob = quote_id.encode() + b":" + measurement.encode()
        else:
            blob = b"quote"
        quote = AttestationQuote(
            quote_id=quote_id,
            enclave_id=target_enclave,
            quote_blob=blob,
            measurement=measurement,
            status=AttestationStatus.VALID,
        )
        if self.signing_key:
            quote.sign(self.signing_key)
        return quote


class AttestationVerifier:
    """Verify remote attestation quotes against a policy."""

    def __init__(
        self,
        allowed_measurements: set[str] | frozenset[str] | None = None,
        require_signature: bool = False,
    ) -> None:
        self.allowed_measurements: set[str] = set(allowed_measurements) if allowed_measurements else set()
        self.require_signature = require_signature

    def verify(
        self,
        quote: AttestationQuote,
        expected_measurement: str | None = None,
    ) -> bool:
        """Return True for a valid, non-expired quote matching the policy."""
        if quote.status not in {AttestationStatus.VALID}:
            return False
        if quote.is_expired():
            return False
        if not quote.quote_blob:
            return False
        if self.require_signature and not quote.verify_signature():
            return False
        if not self.require_signature and quote.signature and not quote.verify_signature():
            return False
        if expected_measurement is not None and quote.measurement != expected_measurement:
            return False
        if self.allowed_measurements and quote.measurement not in self.allowed_measurements:
            return False
        return True


def verify_quote(
    quote: AttestationQuote,
    allowed_measurements: set[str] | frozenset[str] | None = None,
    *,
    expected_measurement: str | None = None,
    require_signature: bool = False,
) -> bool:
    """Top-level helper to verify a quote."""
    verifier = AttestationVerifier(allowed_measurements, require_signature=require_signature)
    return verifier.verify(quote, expected_measurement=expected_measurement)
