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
import shutil
import tempfile
import threading
import time
from datetime import UTC, datetime
from typing import Any

import filelock

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Group-writable lock file mode so that services running as different users
# (e.g. root for CLI / systemd prep, aitbc for daemons) can share the lock on
# /var/lib/aitbc/api_keys.json. The /var/lib/aitbc directory is setgid aitbc,
# so new files inherit the aitbc group.
_LOCK_FILE_MODE = 0o660

# Deferred usage stats are folded into the JSON store at most this often;
# every validate used to fsync-rewrite the whole file.
_USAGE_FLUSH_SECONDS = 300.0


class CorruptKeyStoreError(RuntimeError):
    """api_keys.json is unreadable JSON — it must never be treated as an
    empty store and never overwritten (a truncated write would otherwise
    erase every key for good, APIKEY-STORE-ATOMIC-1)."""


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
        self._lock_path = f"{self.storage_path}.lock"
        self._prepare_lock_file()
        self._lock = filelock.FileLock(self._lock_path, mode=_LOCK_FILE_MODE)
        # key-hash -> {"last_used": str, "usage_count": int} pending a flush
        self._usage: dict[str, dict[str, Any]] = {}
        self._usage_flushed_at = time.monotonic()
        with self._lock:
            self.api_keys: dict[str, Any] = self._load_keys()

    def _prepare_lock_file(self) -> None:
        """Create or chmod the lock file so all aitbc-group services can use it."""
        try:
            if not os.path.exists(self._lock_path):
                # Create the file atomically with group-writable mode.  The
                # parent directory is setgid aitbc, so the group is aitbc.
                fd = os.open(self._lock_path, os.O_CREAT | os.O_WRONLY, _LOCK_FILE_MODE)
                os.close(fd)
                return

            st = os.stat(self._lock_path)
            current_mode = st.st_mode & 0o777
            if current_mode != _LOCK_FILE_MODE and st.st_uid == os.geteuid():
                os.chmod(self._lock_path, _LOCK_FILE_MODE)
        except (OSError, PermissionError):
            # If we cannot fix the lock file, FileLock acquisition will report
            # the real error with a useful path.
            pass

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
        except json.JSONDecodeError as e:
            self._quarantine_corrupt_file(e)
            raise CorruptKeyStoreError(f"{self.storage_path} is not readable JSON") from e
        except (OSError, KeyError, TypeError) as e:
            logger.error("Error loading API keys: %s", e)
        return {}

    def _quarantine_corrupt_file(self, cause: BaseException) -> None:
        """Preserve the unreadable store beside a .corrupt copy and log it.

        Never overwrite an existing .corrupt file — the first copy is the
        forensic one; later corruptions get a timestamped sibling.
        """
        corrupt_path = f"{self.storage_path}.corrupt"
        try:
            if os.path.exists(corrupt_path):
                corrupt_path = f"{self.storage_path}.{int(time.time())}.corrupt"
            shutil.copy2(self.storage_path, corrupt_path)
        except OSError as copy_error:
            logger.critical("API key store at %s is corrupt AND could not be preserved: %s", self.storage_path, copy_error)
        else:
            logger.critical(
                "API key store at %s is corrupt (%s); preserved as %s. Refusing to read it as empty or overwrite it — restore it or delete it deliberately.",
                self.storage_path,
                cause,
                corrupt_path,
            )

    @staticmethod
    def _looks_like_digest(key: str) -> bool:
        """Heuristic to detect already-hashed keys (64-char hex digest)."""
        return len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key)

    def _save_keys(self) -> bool:
        """Save API keys to persistent storage, atomically.

        Write-temp-fsync-replace: a kill mid-write leaves either the old file
        or the new one, never a truncated mix. The temp file is created mode
        0600 (mkstemp default, chmod'ed explicitly before the replace) in the
        store's own directory so os.replace is same-filesystem atomic.
        Returns False on a logged write failure.

        This is the unguarded write helper; callers must hold ``self._lock``.
        """
        directory = os.path.dirname(self.storage_path) or "."
        tmp_path = ""
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".api_keys.", suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(self.api_keys, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self.storage_path)
            return True
        except (OSError, TypeError) as e:
            logger.error("Error saving API keys: %s", e)
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return False

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
        except CorruptKeyStoreError:
            return {"status": "error", "message": "API key store is corrupt; refusing to operate"}
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
                # usage stats live in memory and flush periodically — a
                # successful validate must not fsync-rewrite the key file
                # under the blocking FileLock on the async hot path.
                usage = self._usage.setdefault(matched_key, {"last_used": None, "usage_count": 0})
                usage["last_used"] = datetime.now(UTC).isoformat()
                usage["usage_count"] += 1
                self._maybe_flush_usage()
                return {
                    "status": "success",
                    "valid": True,
                    "user_id": key_data["user_id"],
                    "permissions": key_data["permissions"],
                    "usage_count": int(key_data.get("usage_count") or 0) + usage["usage_count"],
                }
        except CorruptKeyStoreError:
            return {"status": "error", "valid": False, "message": "API key store is corrupt; refusing to operate"}
        except (OSError, TypeError, KeyError) as e:
            logger.error("Error validating API key: %s", e)
            return {"status": "error", "message": "API key validation failed"}

    def _maybe_flush_usage(self) -> None:
        """Fold deferred usage counters into the store once per interval.

        Callers must hold ``self._lock``. Deltas survive a failed save and
        ride the next flush; counters in the response always read persisted
        + pending so callers see monotonic values.
        """
        if not self._usage or time.monotonic() - self._usage_flushed_at < _USAGE_FLUSH_SECONDS:
            return
        for key_hash, usage in self._usage.items():
            data = self.api_keys.get(key_hash)
            if data is None:
                continue
            data["usage_count"] = int(data.get("usage_count") or 0) + usage["usage_count"]
            data["last_used"] = usage["last_used"]
        if self._save_keys():
            self._usage.clear()
        self._usage_flushed_at = time.monotonic()

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
        except CorruptKeyStoreError:
            return {"status": "error", "message": "API key store is corrupt; refusing to operate"}
        except (OSError, TypeError, KeyError) as e:
            logger.error("Error revoking API key: %s", e)
            return {"status": "error", "message": "API key revocation failed"}


# Global instance (agent-coordinator compatibility), created lazily on first
# access: APIKeyManager() creates <storage_path>.lock and reads the key file,
# so eager construction made a bare ``import aitbc.auth`` write to
# /var/lib/aitbc. The name ``api_key_manager`` resolves through module
# __getattr__ and still yields a real APIKeyManager instance.
_api_key_manager: APIKeyManager | None = None
_api_key_manager_lock = threading.Lock()


def get_api_key_manager() -> APIKeyManager:
    global _api_key_manager
    if _api_key_manager is None:
        with _api_key_manager_lock:
            if _api_key_manager is None:
                _api_key_manager = APIKeyManager()
    return _api_key_manager


def __getattr__(name: str) -> Any:
    if name == "api_key_manager":
        return get_api_key_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# api_key_manager resolves through __getattr__ above — F822 is a false positive.
__all__ = ["APIKeyManager", "api_key_manager", "get_api_key_manager"]  # noqa: F822
