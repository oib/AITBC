"""Memory service business logic.

In-memory storage only. Persistence, distributed replication, and key
management are upgrade paths for future releases.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aitbc.agent_memory.models import (
    ContentAddressedBlob,
    ReplicationProof,
    ReplicationStatus,
)
from aitbc.aitbc_logging import get_logger

from .config import settings

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = get_logger(__name__)


def _derive_fernet_key(master_key: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from the configured master key.

    Uses PBKDF2-HMAC-SHA256 with the provided salt instead of a raw SHA-256 digest,
    which closes the unsalted-KDF finding while remaining Fernet-compatible.

    The salt is generated per store instance. Because this service is in-memory
    only, a per-process salt is acceptable; persistence would require storing the
    salt alongside each encrypted blob.
    """
    digest = hashlib.pbkdf2_hmac("sha256", master_key.encode("utf-8"), salt, 100_000, dklen=32)
    return base64.urlsafe_b64encode(digest)


def _compute_content_address(data: bytes) -> str:
    """Return the canonical SHA-256 content address for ``data``."""
    return f"cid:{hashlib.sha256(data).hexdigest()}"


class MemoryStore:
    """In-memory content-addressed blob store with encryption-at-rest hooks."""

    _fernet: Fernet | None

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._master_key: str | None = settings.memory_master_key
        # Per-instance salt. For an in-memory service this is fine; persisted storage
        # would require storing the salt with each encrypted blob.
        self._salt: bytes = secrets.token_bytes(16)
        self._fernet = None
        if self._master_key:
            try:
                from cryptography.fernet import Fernet

                self._fernet = Fernet(_derive_fernet_key(self._master_key, self._salt))
                logger.info("Memory service: encryption-at-rest enabled")
            except Exception as e:
                logger.warning("Memory service: failed to initialize Fernet: %s", e)
                self._master_key = None
        if not self._master_key:
            logger.warning("Memory service: MEMORY_MASTER_KEY is not set; blobs are stored as plaintext")

    def store_blob(self, owner: str, data: bytes, tags: dict[str, Any] | None = None) -> ContentAddressedBlob:
        """Store a blob and return its content-addressed descriptor."""
        content_address = _compute_content_address(data)
        stored_data = data
        encrypted = self._fernet is not None
        if self._fernet:
            stored_data = self._fernet.encrypt(data)
        self._store[content_address] = {
            "content_address": content_address,
            "owner": owner,
            "size": len(data),
            "stored_data": stored_data,
            "encrypted": encrypted,
            "tags": tags or {},
            "created_at": datetime.now(UTC),
        }
        return ContentAddressedBlob(
            content_address=content_address,
            owner=owner,
            size=len(data),
            tags=tags or {},
            created_at=self._store[content_address]["created_at"],
        )

    def retrieve_blob(self, content_address: str) -> tuple[bytes, ContentAddressedBlob]:
        """Retrieve the original bytes and descriptor for a stored blob."""
        record = self._store.get(content_address)
        if not record:
            raise KeyError(f"Blob not found: {content_address}")
        data = record["stored_data"]
        if record["encrypted"] and self._fernet:
            data = self._fernet.decrypt(data)
        blob = ContentAddressedBlob(
            content_address=record["content_address"],
            owner=record["owner"],
            size=record["size"],
            tags=record["tags"],
            created_at=record["created_at"],
        )
        return data, blob

    def health(self) -> dict[str, Any]:
        """Return a simple health/status payload."""
        return {
            "status": "healthy",
            "stored_blobs": len(self._store),
            "encrypted_at_rest": self._fernet is not None,
        }

    def replicate(self, content_address: str, node_id: str) -> ReplicationProof:
        """Return a replication proof hook for a storage node."""
        record = self._store.get(content_address)
        status = ReplicationStatus.VALID if record else ReplicationStatus.INVALID
        return ReplicationProof(
            proof_id=f"proof-{hashlib.sha256(f'{content_address}:{node_id}'.encode()).hexdigest()[:12]}",
            content_address=content_address,
            node_id=node_id,
            status=status,
        )
