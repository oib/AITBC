"""TEE attestation quote generation/validation skeleton (v0.14.1 §A1).

Real quote handling requires platform-specific libraries (Intel SGX/V2, TDX,
AMD SEV, etc.). The Ed25519 signing layer here is a simulator-friendly
stand-in for a quote signed inside the enclave and verified by the platform
attestation service.

v0.14.3: Quotes are now self-contained signed documents that can be
serialized to/from base64 JSON, transmitted to the coordinator, and verified
with a public key carried in the quote itself. This enforces a real quote
path before escrow release.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import json
import os
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-serializable dict."""
        return {
            "quote_id": self.quote_id,
            "enclave_id": self.enclave_id,
            "quote_blob": base64.b64encode(self.quote_blob).decode("ascii"),
            "measurement": self.measurement,
            "timestamp": self.timestamp.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "signature": base64.b64encode(self.signature).decode("ascii") if self.signature else "",
            "public_key": base64.b64encode(self.public_key).decode("ascii") if self.public_key else "",
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttestationQuote:
        """Deserialize from a JSON-serializable dict."""

        def _parse_dt(value: str | datetime) -> datetime:
            if isinstance(value, datetime):
                return value
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

        def _b64_bytes(value: str) -> bytes:
            if not value:
                return b""
            return base64.b64decode(value)

        return cls(
            quote_id=data.get("quote_id", ""),
            enclave_id=data.get("enclave_id", ""),
            quote_blob=_b64_bytes(data.get("quote_blob", "")),
            measurement=data.get("measurement", ""),
            timestamp=_parse_dt(data["timestamp"]),
            expires_at=_parse_dt(data["expires_at"]),
            status=AttestationStatus(data.get("status", "valid")),
            signature=_b64_bytes(data.get("signature", "")),
            public_key=_b64_bytes(data.get("public_key", "")),
            meta=data.get("meta", {}),
        )

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> AttestationQuote:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(text))

    def to_base64(self) -> str:
        """Serialize to a base64-encoded JSON string."""
        return base64.b64encode(self.to_json().encode()).decode("ascii")

    @classmethod
    def from_base64(cls, text: str) -> AttestationQuote:
        """Deserialize from a base64-encoded JSON string."""
        return cls.from_json(base64.b64decode(text).decode("utf-8"))


class QuoteGenerator:
    """Generate local attestation quotes for an enclave."""

    def __init__(self, enclave_id: str = "", signing_key: bytes | None = None) -> None:
        self.enclave_id = enclave_id
        self.signing_key = signing_key

    def _resolve_signing_key(self, enclave_id: str) -> bytes:
        """Return the Ed25519 signing key material for this enclave.

        If the caller supplied a key, use it -- this is how a real deployment
        would pass in the enclave's actual hardware-rooted key, and it is how
        a caller that wants a *stable* identity across calls (so it can be
        pinned via ``EnclaveIdentity`` registration, see the coordinator's
        ``tee`` context) should use this class.

        Otherwise generate fresh random key material. Security fix
        (2026-08-24): this used to derive a deterministic seed from
        ``enclave_id`` alone. ``enclave_id`` is caller-supplied, public data
        (it travels in job constraints and in the quote itself), so that
        derivation let anyone who knew or guessed an enclave_id compute the
        exact signing key a legitimate quote for it would use, and forge one
        of their own -- with zero secret material. A quote signed with this
        random fallback is still only self-consistent (see
        ``AttestationQuote.verify_signature``), never pinned to a registered
        identity on its own; callers that need continuity across calls must
        supply ``signing_key`` explicitly.
        """
        if self.signing_key is not None:
            return self.signing_key
        return os.urandom(32)

    def generate(
        self,
        quote_id: str = "",
        enclave_id: str = "",
        measurement: str = "",
        report_data: bytes = b"",
    ) -> AttestationQuote:
        """Return a signed quote for the given enclave and measurement.

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
        # v0.14.3: always sign unless explicitly disabled with an empty key.
        signing_key = self._resolve_signing_key(target_enclave)
        if signing_key:
            quote.sign(signing_key)
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
        known_public_key: bytes | None = None,
    ) -> bool:
        """Return True for a valid, non-expired quote matching the policy.

        ``known_public_key``, when supplied, pins verification to a
        previously-registered identity: the quote's embedded public key must
        match it exactly, not merely be internally self-consistent. Without
        it, this only checks that the quote's signature matches the public
        key carried in the quote itself -- which any holder of any keypair
        can produce, so on its own it proves the quote was not altered in
        transit, nothing about who signed it.
        """
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
        if known_public_key is not None and quote.public_key != known_public_key:
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
    known_public_key: bytes | None = None,
) -> bool:
    """Top-level helper to verify a quote."""
    verifier = AttestationVerifier(allowed_measurements, require_signature=require_signature)
    return verifier.verify(quote, expected_measurement=expected_measurement, known_public_key=known_public_key)
