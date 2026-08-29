"""Sealed data-at-rest helpers for TEE enclaves (v0.14.1 §A3).

Provides ``SealedBlob`` and ``seal`` / ``unseal`` functions that use AES-GCM
via the ``cryptography`` package. The seal is bound to an enclave
identity/measurement by including it in the key derivation.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import TEEError

#: AES-GCM tag size in bytes.
GCM_TAG_SIZE = 16


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


def _derive_key(measurement: str, secret: bytes) -> bytes:
    """Derive a 32-byte sealing key from a measurement and a caller-supplied secret."""
    if not secret:
        raise ValueError("secret is required")
    return sha256(secret + measurement.encode("utf-8")).digest()


def _make_nonce(blob_id: str) -> bytes:
    """Generate a deterministic 12-byte AES-GCM nonce for ``blob_id``.

    The nonce is derived from the blob id and truncated to the AES-GCM
    recommended size. AES-GCM must never reuse the same (key, nonce) pair, so
    the caller must ensure ``blob_id`` is unique within the scope of a secret.
    """
    return sha256(blob_id.encode("utf-8")).digest()[:12]


def seal(
    blob_id: str,
    enclave_id: str,
    measurement: str,
    plaintext: bytes,
    *,
    secret: bytes,
    nonce: bytes | None = None,
) -> SealedBlob:
    """Seal ``plaintext`` so it can only be unsealed by the same measurement.

    ``secret`` is the 32-byte platform sealing key and is required.
    ``nonce`` is generated from ``blob_id`` if not provided.
    """
    if not plaintext:
        raise ValueError("plaintext cannot be empty")
    key = _derive_key(measurement, secret)
    if nonce is None:
        nonce = _make_nonce(blob_id)
    if len(nonce) != 12:
        raise ValueError("nonce must be 12 bytes for AES-GCM")

    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(nonce, plaintext, None)
    ciphertext = encrypted[:-GCM_TAG_SIZE]
    tag = encrypted[-GCM_TAG_SIZE:]

    return SealedBlob(
        blob_id=blob_id,
        enclave_id=enclave_id,
        measurement=measurement,
        ciphertext=base64.b64encode(ciphertext),
        tag=tag,
        nonce=nonce,
    )


def unseal(blob: SealedBlob, *, secret: bytes) -> bytes:
    """Unseal a ``SealedBlob`` and verify its AES-GCM tag."""
    key = _derive_key(blob.measurement, secret)
    ciphertext = base64.b64decode(blob.ciphertext)
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(blob.nonce, ciphertext + blob.tag, None)
    except InvalidTag as e:
        raise TEEError("sealed blob integrity check failed") from e
