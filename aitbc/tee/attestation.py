"""TEE attestation quote generation/validation skeleton (v0.14.1 §A1).

ponytail: This is a skeleton. Real quote handling requires platform-specific
libraries (Intel SGX/V2, TDX, AMD SEV, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


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
    meta: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the quote has expired."""
        if now is None:
            now = datetime.now(UTC)
        if self.status == AttestationStatus.EXPIRED:
            return True
        return self.expires_at <= now


class QuoteGenerator:
    """Generate local attestation quotes for an enclave."""

    def __init__(self, enclave_id: str = "") -> None:
        self.enclave_id = enclave_id

    def generate(
        self,
        quote_id: str = "",
        enclave_id: str = "",
        measurement: str = "",
        report_data: bytes = b"",
    ) -> AttestationQuote:
        """Return a skeleton quote.

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
        return AttestationQuote(
            quote_id=quote_id,
            enclave_id=target_enclave,
            quote_blob=blob,
            measurement=measurement,
            status=AttestationStatus.VALID,
        )


class AttestationVerifier:
    """Verify remote attestation quotes against a policy."""

    def __init__(self, allowed_measurements: set[str] | frozenset[str] | None = None) -> None:
        self.allowed_measurements: set[str] = set(allowed_measurements) if allowed_measurements else set()

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
) -> bool:
    """Top-level helper to verify a quote."""
    if allowed_measurements is not None and expected_measurement is not None:
        return AttestationVerifier(allowed_measurements).verify(quote, expected_measurement=expected_measurement)
    if allowed_measurements is not None:
        return AttestationVerifier(allowed_measurements).verify(quote)
    if expected_measurement is not None:
        return AttestationVerifier().verify(quote, expected_measurement=expected_measurement)
    return AttestationVerifier().verify(quote)
