"""Sealed data-at-rest helpers for TEE enclaves (v0.14.1 §A3).

Provides ``SealedBlob`` and simulator-friendly ``seal`` / ``unseal`` functions.
Production implementations bind the seal to a platform-specific sealing key
derived from the enclave measurement and CPU-bound key hierarchy.
"""

from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from .errors import TEEError


@dataclass
class SealedBlob:
    """A sealed secret bound to an enclave identity/measurement."""

    blob_id: str
    enclave_id: str
    measurement: str
    ciphertext: bytes
    tag: bytes
    nonce: bytes
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.blob_id:
            raise ValueError("blob_id is required")
        if not self.enclave_id:
            raise ValueError("enclave_id is required")
        if not self.measurement:
            raise ValueError("measurement is required")


def _derive_key(measurement: str, secret: bytes = b"") -> bytes:
    """Derive a sealing key from a measurement and optional secret."""
    if not secret:
        secret = measurement.encode("utf-8")
    return sha256(secret + measurement.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate a deterministic keystream for the simulator cipher."""
    stream = b""
    counter = 0
    while len(stream) < length:
        stream += sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        counter += 1
    return stream[:length]


def seal(
    blob_id: str,
    enclave_id: str,
    measurement: str,
    plaintext: bytes,
    secret: bytes = b"",
    nonce: bytes | None = None,
) -> SealedBlob:
    """Seal ``plaintext`` so it can only be unsealed by the same measurement.

    ``secret`` is an optional platform sealing key. ``nonce`` is generated if
    not provided.
    """
    if not plaintext:
        raise ValueError("plaintext cannot be empty")
    key = _derive_key(measurement, secret)
    if nonce is None:
        nonce = sha256(blob_id.encode("utf-8")).digest()[:16]
    ciphertext = bytes(b ^ k for b, k in zip(plaintext, _keystream(key, nonce, len(plaintext)), strict=False))
    tag = hmac.new(key, ciphertext, sha256).digest()
    return SealedBlob(
        blob_id=blob_id,
        enclave_id=enclave_id,
        measurement=measurement,
        ciphertext=base64.b64encode(ciphertext),
        tag=tag,
        nonce=nonce,
    )


def unseal(blob: SealedBlob, secret: bytes = b"") -> bytes:
    """Unseal a ``SealedBlob`` and verify its integrity tag."""
    key = _derive_key(blob.measurement, secret)
    ciphertext = base64.b64decode(blob.ciphertext)
    expected_tag = hmac.new(key, ciphertext, sha256).digest()
    if not hmac.compare_digest(expected_tag, blob.tag):
        raise TEEError("sealed blob integrity check failed")
    return bytes(b ^ k for b, k in zip(ciphertext, _keystream(key, blob.nonce, len(ciphertext)), strict=False))
