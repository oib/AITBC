"""
API key generation and management with persistent storage.

Extracted from ``apps/agent-coordinator/src/app/auth/jwt_handler.py::APIKeyManager``.

Keys are stored as one-way SHA-256 digests; the plaintext key is returned to the
caller exactly once at generation time. Validation uses constant-time digest
comparison to limit timing attacks.

This implementation uses a process-wide file lock (``filelock``) on the storage
file so concurrent callers / multi-worker deployments do not corrupt the JSON
store. Each mutating operation reloads from disk before writing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from typing import Any

import filelock

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class APIKeyManager:
    """API key generation and management with persistent storage.

    Keys are stored in a JSON file (default: ``/var/lib/aitbc/api_keys.json``)
    with ``0600`` permissions. Each digest maps to a dict with user_id,
    permissions, created_at, last_used, and usage_count. The plaintext key is
    never persisted after generation.

    A file lock on ``<storage_path>.lock`` protects all reads and writes so the
    JSON file is safe across processes.
    """

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path: str = (
            storage_path or os.getenv("API_KEY_STORAGE_PATH", "/var/lib/aitbc/api_keys.json") or "/var/lib/aitbc/api_keys.json"
        )
        self._lock = filelock.FileLock(f"{self.storage_path}.lock")
        with self._lock:
            self.api_keys: dict[str, Any] = self._load_keys()

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Return a stable one-way digest for an API key."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def _load_keys(self) -> dict[str, Any]:
        """Load API keys from persistent storage, migrating legacy plaintext keys."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path) as f:
                    data: dict[str, Any] = json.load(f)
                migrated: dict[str, Any] = {}
                needs_save = False
                for key, key_data in data.items():
                    if self._looks_like_digest(key):
                        migrated[key] = key_data
                    else:
                        migrated[self._hash_key(key)] = key_data
                        needs_save = True
                if needs_save:
                    self.api_keys = migrated
                    self._save_keys()
                return migrated
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("Error loading API keys: %s", e)
        return {}

    @staticmethod
    def _looks_like_digest(key: str) -> bool:
        """Heuristic to detect already-hashed keys (64-char hex digest)."""
        return len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key)

    def _save_keys(self) -> None:
        """Save API keys to persistent storage.

        This is the unguarded write helper; callers must hold ``self._lock``.
        """
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.api_keys, f, indent=2)
            os.chmod(self.storage_path, 0o600)
        except (OSError, TypeError) as e:
            logger.error("Error saving API keys: %s", e)

    def _refresh(self) -> None:
        """Reload the in-memory key store from disk.

        Callers must hold ``self._lock``.
        """
        self.api_keys = self._load_keys()

    def _find_key_data(self, api_key: str) -> tuple[str, dict[str, Any] | None]:
        """Look up key data by constant-time comparison of digests.

        Returns the stored hash and the associated data, or the input hash and
        ``None`` if not found.
        """
        key_hash = self._hash_key(api_key)
        matched_key: str | None = None
        matched_data: dict[str, Any] | None = None
        for stored_hash, key_data in self.api_keys.items():
            if hmac.compare_digest(key_hash, stored_hash):
                matched_key = stored_hash
                matched_data = key_data
        return matched_key or key_hash, matched_data

    def generate_api_key(self, user_id: str, permissions: list[str] | None = None) -> dict[str, Any]:
        """Generate new API key for user.

        Returns:
            ``{"status": "success", "api_key": ..., "permissions": ..., "created_at": ...}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            with self._lock:
                self._refresh()
                api_key = secrets.token_urlsafe(32)
                key_hash = self._hash_key(api_key)
                key_data: dict[str, Any] = {
                    "user_id": user_id,
                    "permissions": permissions or [],
                    "created_at": datetime.now(UTC).isoformat(),
                    "last_used": None,
                    "usage_count": 0,
                }
                self.api_keys[key_hash] = key_data
                self._save_keys()
                return {
                    "status": "success",
                    "api_key": api_key,
                    "permissions": permissions or [],
                    "created_at": key_data["created_at"],
                }
        except (OSError, TypeError, KeyError) as e:
            logger.error("Error generating API key: %s", e)
            return {"status": "error", "message": "API key generation failed"}

    def validate_api_key(self, api_key: str) -> dict[str, Any]:
        """Validate API key and return user info.

        Returns:
            ``{"status": "success", "valid": True, "user_id": ..., "permissions": ...}``
            or ``{"status": "error", "valid": False, "message": ...}``
        """
        try:
            with self._lock:
                self._refresh()
                matched_key, key_data = self._find_key_data(api_key)
                if key_data is None:
                    return {"status": "error", "valid": False, "message": "Invalid API key"}
                key_data["last_used"] = datetime.now(UTC).isoformat()
                key_data["usage_count"] += 1
                self._save_keys()
                return {
                    "status": "success",
                    "valid": True,
                    "user_id": key_data["user_id"],
                    "permissions": key_data["permissions"],
                    "usage_count": key_data["usage_count"],
                }
        except (OSError, TypeError, KeyError) as e:
            logger.error("Error validating API key: %s", e)
            return {"status": "error", "message": "API key validation failed"}

    def revoke_api_key(self, api_key: str) -> dict[str, Any]:
        """Revoke API key.

        Returns:
            ``{"status": "success", "message": ...}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            with self._lock:
                self._refresh()
                matched_key, key_data = self._find_key_data(api_key)
                if key_data is not None:
                    del self.api_keys[matched_key]
                    self._save_keys()
                    return {"status": "success", "message": "API key revoked"}
                else:
                    return {"status": "error", "message": "API key not found"}
        except (OSError, TypeError, KeyError) as e:
            logger.error("Error revoking API key: %s", e)
            return {"status": "error", "message": "API key revocation failed"}


# Global instance (agent-coordinator compatibility)
api_key_manager = APIKeyManager()


__all__ = ["APIKeyManager", "api_key_manager"]
