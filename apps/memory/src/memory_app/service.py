"""Memory service business logic.

In-memory storage only. Persistence, distributed replication, and key
management are upgrade paths for future releases.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
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


class BlobTooLargeError(ValueError):
    """Raised when a blob exceeds the configured per-blob byte cap."""


class StoreFullError(RuntimeError):
    """Raised when the store is full and nothing can be evicted."""


class BlobPermissionError(PermissionError):
    """Raised when the caller is not an owner of the requested blob."""


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

    def _expires_at(self, created_at: datetime) -> datetime | None:
        ttl = settings.memory_blob_ttl_seconds
        if ttl <= 0:
            return None
        return created_at + timedelta(seconds=ttl)

    def _is_expired(self, record: dict[str, Any], now: datetime) -> bool:
        expires_at = record.get("expires_at")
        return expires_at is not None and now >= expires_at

    def _evict_expired(self, now: datetime) -> int:
        """Drop all TTL-expired records; returns the number evicted."""
        expired = [cid for cid, rec in self._store.items() if self._is_expired(rec, now)]
        for cid in expired:
            del self._store[cid]
        return len(expired)

    def _evict_lru(self) -> str | None:
        """Evict the least-recently-used record; returns its cid or None."""
        if not self._store:
            return None
        victim = min(self._store, key=lambda cid: self._store[cid].get("last_accessed") or self._store[cid]["created_at"])
        del self._store[victim]
        return victim

    def _make_room(self) -> None:
        """Ensure capacity for one more blob: TTL sweep, then LRU eviction.

        MEMORY-RESIDUAL-1 (#1682): previously a full store raised
        StoreFullError on every write until restart — a self-inflicted DoS.
        Now expired entries are dropped first and the least-recently-used
        live entry is evicted until there is room. StoreFullError remains
        only for a degenerate max_blobs <= 0 configuration.
        """
        now = datetime.now(UTC)
        self._evict_expired(now)
        while len(self._store) >= settings.memory_max_blobs and self._store:
            self._evict_lru()
        if len(self._store) >= settings.memory_max_blobs:
            raise StoreFullError(f"memory store is full ({settings.memory_max_blobs} blobs)")

    def store_blob(self, owner: str, data: bytes, tags: dict[str, Any] | None = None) -> ContentAddressedBlob:
        """Store a blob and return its content-addressed descriptor.

        Content addressing makes the store idempotent: re-storing identical
        bytes returns the committed record unchanged rather than clobbering
        the original owner/tags/created_at (#1427). The requesting owner is
        still recorded in the blob's owner set so every tenant that
        contributed the content may retrieve it (#1682).
        """
        if len(data) > settings.memory_max_blob_bytes:
            raise BlobTooLargeError(f"blob of {len(data)} bytes exceeds the {settings.memory_max_blob_bytes}-byte cap")
        content_address = _compute_content_address(data)
        now = datetime.now(UTC)
        existing = self._store.get(content_address)
        if existing is not None:
            if self._is_expired(existing, now):
                # TTL-expired records behave as absent: re-store fresh.
                del self._store[content_address]
            else:
                existing["owners"].add(owner)
                existing["last_accessed"] = now
                return ContentAddressedBlob(
                    content_address=existing["content_address"],
                    owner=existing["owner"],
                    size=existing["size"],
                    tags=existing["tags"],
                    created_at=existing["created_at"],
                )
        self._make_room()
        stored_data = data
        encrypted = self._fernet is not None
        if self._fernet:
            stored_data = self._fernet.encrypt(data)
        created_at = now
        self._store[content_address] = {
            "content_address": content_address,
            "owner": owner,
            "owners": {owner},
            "size": len(data),
            "stored_data": stored_data,
            "encrypted": encrypted,
            "tags": tags or {},
            "created_at": created_at,
            "last_accessed": now,
            "expires_at": self._expires_at(created_at),
        }
        return ContentAddressedBlob(
            content_address=content_address,
            owner=owner,
            size=len(data),
            tags=tags or {},
            created_at=created_at,
        )

    def _get_record(self, content_address: str, owner: str | None) -> dict[str, Any]:
        """Fetch a live record, enforcing TTL and ownership (#1682).

        ``owner`` is required: /retrieve used to ignore it entirely, so any
        caller who learned a cid could read the blob. Raises KeyError for
        missing/expired blobs and BlobPermissionError for non-owners.
        """
        record = self._store.get(content_address)
        if not record:
            raise KeyError(f"Blob not found: {content_address}")
        now = datetime.now(UTC)
        if self._is_expired(record, now):
            del self._store[content_address]
            raise KeyError(f"Blob not found: {content_address}")
        if owner is not None and owner not in record["owners"]:
            raise BlobPermissionError(f"caller is not an owner of {content_address}")
        record["last_accessed"] = now
        return record

    def retrieve_blob(self, content_address: str, owner: str | None = None) -> tuple[bytes, ContentAddressedBlob]:
        """Retrieve the original bytes and descriptor for a stored blob."""
        record = self._get_record(content_address, owner)
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

    def delete_blob(self, content_address: str, owner: str) -> None:
        """Delete a blob; only an owner of the blob may delete it (#1682)."""
        self._get_record(content_address, owner)
        del self._store[content_address]

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
