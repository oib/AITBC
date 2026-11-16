"""
Key management service for confidential transactions
"""

import asyncio
import base64
import hmac
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import aiofiles

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from aitbc.aitbc_logging import get_logger

from ....config import settings
from ....schemas import KeyPair, KeyRotationLog

logger = get_logger(__name__)


class KeyManagementError(Exception):
    """Base exception for key management errors"""

    pass


class KeyNotFoundError(KeyManagementError):
    """Raised when key is not found"""

    pass


class AccessDeniedError(KeyManagementError):
    """Raised when access is denied"""

    pass


# Expected failure surface for the key-management helpers: filesystem/JSON,
# data-shape, runtime and the module error hierarchy (which also covers
# NotImplementedError via RuntimeError). BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    KeyManagementError,
)

# #1932 F1: participant_id is interpolated into key-storage filenames
# ("{participant_id}.json" / ".priv" / revoked/). Restrict it to the same
# safe-component charset used for systemd unit names
# (_SAFE_UNIT_COMPONENT_RE in agent_coordination/services/integration.py):
# a leading alphanumeric plus [A-Za-z0-9._-] means "..", "/" and other
# separators can never traverse out of key_storage_dir. Enforced at the
# storage layer so every caller — admin or client — is covered.
_PARTICIPANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


class _SyncAuditLoadUnsupported:
    """Sentinel type: storage backend has no synchronous audit-key loader."""


_SYNC_AUDIT_LOAD_UNSUPPORTED = _SyncAuditLoadUnsupported()


def validate_participant_id(participant_id: str) -> str:
    """Return participant_id when it is filename-safe, else raise ValueError."""
    if not isinstance(participant_id, str) or not _PARTICIPANT_ID_RE.fullmatch(participant_id):
        raise ValueError(f"Invalid participant_id: {participant_id!r}")
    return participant_id


class KeyManager:
    """Manages encryption keys for confidential transactions"""

    def __init__(self, storage_backend: "KeyStorageBackend"):
        self.storage = storage_backend
        self.backend = default_backend()
        self._key_cache: dict[str, Any] = {}
        self._audit_key: X25519PublicKey | None = None
        self._audit_private: bytes | None = None
        self._audit_key_rotation = timedelta(days=30)
        # #2162: in-flight audit-key storage/load tasks. A generated audit
        # key must never be lost silently, and a persisted one must be
        # loaded before any regeneration.
        self._audit_load_task: asyncio.Task[KeyPair | None] | None = None
        self._audit_store_task: asyncio.Task[bool] | None = None

    async def generate_key_pair(self, participant_id: str) -> KeyPair:
        """Generate X25519 key pair for participant"""
        try:
            private_key = X25519PrivateKey.generate()
            public_key = private_key.public_key()
            key_pair = KeyPair(
                participant_id=participant_id,
                private_key=private_key.private_bytes_raw(),
                public_key=public_key.public_bytes_raw(),
                algorithm="X25519",
                created_at=datetime.now(UTC),
                version=1,
            )
            await self.storage.store_key_pair(key_pair)
            self._key_cache[participant_id] = {"public_key": public_key, "version": key_pair.version}
            logger.info("Generated key pair for participant: %s", participant_id)
            return key_pair
        except _OPS_ERRORS as e:
            logger.error("Failed to generate key pair for %s: %s", participant_id, e)
            raise KeyManagementError(f"Key generation failed: {e}") from e

    async def rotate_keys(self, participant_id: str) -> KeyPair:
        """Rotate encryption keys for participant"""
        try:
            current_key = await self.storage.get_key_pair(participant_id)
            if not current_key:
                raise KeyNotFoundError(f"No existing keys for {participant_id}")
            new_key_pair = await self.generate_key_pair(participant_id)
            new_key_pair.version = current_key.version + 1
            await self.storage.store_key_pair(new_key_pair)
            self._key_cache[participant_id] = {
                "public_key": X25519PublicKey.from_public_bytes(new_key_pair.public_key),
                "version": new_key_pair.version,
            }
            rotation_log = KeyRotationLog(
                participant_id=participant_id,
                old_version=current_key.version,
                new_version=new_key_pair.version,
                rotated_at=datetime.now(UTC),
                reason="scheduled_rotation",
            )
            await self.storage.log_rotation(rotation_log)
            try:
                await self._reencrypt_transactions(participant_id, current_key, new_key_pair)
            except _OPS_ERRORS:
                # Roll back to the *original* key pair, not to the new one carrying the old
                # version number. The previous code did the latter -- it restored
                # `new_key_pair.version` and stored `new_key_pair`, so a rotation that
                # reported failure had still replaced the participant's key material and
                # permanently destroyed access to everything encrypted under the old key.
                # Re-encryption is unimplemented, so this path is the only one rotation takes.
                await self.storage.store_key_pair(current_key)
                self._key_cache.pop(participant_id, None)
                raise
            logger.info("Rotated keys for participant: %s", participant_id)
            return new_key_pair
        except (KeyManagementError, NotImplementedError):
            # NotImplementedError passes through rather than being wrapped. The router has
            # an `except NotImplementedError -> 501` arm that could never fire while this
            # wrapped it as KeyManagementError, so the endpoint answered 400 -- and with
            # `detail=str(e)`, meaning the internal message reached the client where every
            # sibling handler returns "Internal server error". 501 is also the honest status
            # for a feature that is documented as unimplemented.
            raise
        except _OPS_ERRORS as e:
            logger.error("Failed to rotate keys for %s: %s", participant_id, e)
            raise KeyManagementError(f"Key rotation failed: {e}") from e

    def get_public_key(self, participant_id: str) -> X25519PublicKey:
        """Get public key for participant"""
        if participant_id in self._key_cache:
            return self._key_cache[participant_id]["public_key"]  # type: ignore[no-any-return]
        key_pair = self.storage.get_key_pair_sync(participant_id)
        if not key_pair:
            raise KeyNotFoundError(f"No keys found for participant: {participant_id}")
        public_key = X25519PublicKey.from_public_bytes(key_pair.public_key)
        self._key_cache[participant_id] = {"public_key": public_key, "version": key_pair.version}
        return public_key

    def get_private_key(self, participant_id: str) -> X25519PrivateKey:
        """Get private key for participant (from secure storage)"""
        key_pair = self.storage.get_key_pair_sync(participant_id)
        if not key_pair:
            raise KeyNotFoundError(f"No keys found for participant: {participant_id}")
        private_key = X25519PrivateKey.from_private_bytes(key_pair.private_key)
        return private_key

    def get_audit_key(self) -> X25519PublicKey:
        """Get public audit key for escrow (synchronous for tests)."""
        self._ensure_audit_key()
        if self._should_rotate_audit_key():
            self._generate_audit_key_in_memory()
        return self._audit_key  # type: ignore[return-value]

    def get_audit_private_key_sync(self, authorization: str) -> X25519PrivateKey:
        """Get private audit key with authorization (sync helper)."""
        if not self.verify_audit_authorization_sync(authorization):
            raise AccessDeniedError("Invalid audit authorization")
        self._ensure_audit_key()
        return X25519PrivateKey.from_private_bytes(self._audit_private)  # type: ignore[arg-type]

    async def get_audit_private_key(self, authorization: str) -> X25519PrivateKey:
        """Async wrapper for audit private key."""
        # #2162: if a persisted-key load was scheduled on this loop by a
        # sync accessor (async-only storage backend), wait for it here so
        # the persisted key — not a fresh one — is returned.
        task = self._audit_load_task
        if task is not None and not task.done():
            try:
                await task
            except _OPS_ERRORS as e:
                logger.debug("Audit key preload failed: %s", e)
            except asyncio.CancelledError:
                pass
        return self.get_audit_private_key_sync(authorization)

    def verify_audit_authorization_sync(self, authorization: str) -> bool:
        """Verify audit authorization token (sync helper)."""
        try:
            auth_data = base64.b64decode(authorization).decode()
            auth_json = json.loads(auth_data)
            expires_at = datetime.fromisoformat(auth_json["expires_at"])
            if expires_at.tzinfo is None:
                # Tokens minted before the aware-UTC convention (or by older
                # issuers) carry naive ISO strings; they are UTC (#1575).
                expires_at = expires_at.replace(tzinfo=UTC)
            if datetime.now(UTC) > expires_at:
                return False
            required_fields = ["issuer", "subject", "expires_at", "signature"]
            if not all(field in auth_json for field in required_fields):
                return False
            secret = settings.hmac_secret or settings.jwt_secret
            if not secret:
                return False
            signature = auth_json.pop("signature")
            expected = hmac.new(secret.encode(), json.dumps(auth_json, sort_keys=True).encode(), "sha256").hexdigest()
            return hmac.compare_digest(signature, expected)
        except _OPS_ERRORS as e:
            logger.error("Failed to verify audit authorization: %s", e)
            return False

    async def verify_audit_authorization(self, authorization: str) -> bool:
        """Verify audit authorization token (async API)."""
        return self.verify_audit_authorization_sync(authorization)

    async def create_audit_authorization(self, issuer: str, purpose: str, expires_in_hours: int = 24) -> str:
        """Create audit authorization token"""
        try:
            payload = {
                "issuer": issuer,
                "subject": "audit_access",
                "purpose": purpose,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=expires_in_hours)).isoformat(),
            }
            secret = settings.hmac_secret or settings.jwt_secret
            if not secret:
                raise KeyManagementError("Audit signing secret not configured")
            payload["signature"] = hmac.new(
                secret.encode(), json.dumps(payload, sort_keys=True).encode(), "sha256"
            ).hexdigest()
            auth_json = json.dumps(payload, sort_keys=True)
            return base64.b64encode(auth_json.encode()).decode()
        except _OPS_ERRORS as e:
            logger.error("Failed to create audit authorization: %s", e)
            raise KeyManagementError(f"Authorization creation failed: {e}") from e

    async def list_participants(self) -> list[str]:
        """List all participants with keys"""
        return await self.storage.list_participants()

    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke participant's keys"""
        try:
            success = await self.storage.revoke_keys(participant_id, reason)
            if success:
                if participant_id in self._key_cache:
                    del self._key_cache[participant_id]
                logger.info("Revoked keys for participant: %s", participant_id)
            return success
        except _OPS_ERRORS as e:
            logger.error("Failed to revoke keys for %s: %s", participant_id, e)
            return False

    def _generate_audit_key_in_memory(self) -> None:
        """Generate and cache an audit key (in-memory for tests/dev)."""
        try:
            audit_private = X25519PrivateKey.generate()
            audit_public = audit_private.public_key()
            self._audit_private = audit_private.private_bytes_raw()
            audit_key_pair = KeyPair(
                participant_id="audit",
                private_key=self._audit_private,
                public_key=audit_public.public_bytes_raw(),
                algorithm="X25519",
                created_at=datetime.now(UTC),
                version=1,
            )
            try:
                store = getattr(self.storage, "store_audit_key", None)
                if store is not None:
                    if asyncio.iscoroutinefunction(store):
                        try:
                            asyncio.get_running_loop()
                        except RuntimeError:
                            # No loop running (sync route / worker thread).
                            if asyncio.run(store(audit_key_pair)) is False:
                                logger.warning("Audit key persistence reported failure")
                        else:
                            # #2162: a loop IS running — schedule the write on
                            # it instead of dropping it. A generated audit key
                            # must never be lost silently.
                            task = asyncio.ensure_future(store(audit_key_pair))
                            self._audit_store_task = task
                            task.add_done_callback(self._on_audit_store_done)
                    elif store(audit_key_pair) is False:
                        logger.warning("Audit key persistence reported failure")
                else:
                    logger.debug("Storage backend has no store_audit_key; audit key stays in memory")
            except _OPS_ERRORS as e:
                logger.warning("Audit key persistence failed: %s", e)
            self._audit_key = audit_public
        except _OPS_ERRORS as e:
            logger.error("Failed to generate audit key: %s", e)
            raise KeyManagementError(f"Audit key generation failed: {e}") from e

    def _ensure_audit_key(self) -> None:
        """Load the persisted audit key, generating + persisting one if absent.

        #2162: previously this always generated a fresh keypair, orphaning
        every audit signature made before a restart. Now a persisted key is
        loaded first; generation only happens when no usable persisted key
        exists.
        """
        if self._audit_key is not None and self._audit_private is not None:
            return
        self._settle_audit_load_task()
        if self._audit_key is not None and self._audit_private is not None:
            return
        if self._load_persisted_audit_key():
            return
        if self._audit_load_task is not None:
            # An async-only backend inside a running loop: the load is
            # scheduled but cannot be awaited from this sync accessor.
            # Generating now could overwrite a persisted key we have not
            # read yet, so refuse rather than risk orphaning it.
            raise KeyManagementError(
                "Persisted audit key load is pending on the event loop; "
                "use the async audit accessor or retry after the loop yields"
            )
        self._generate_audit_key_in_memory()

    def _settle_audit_load_task(self) -> None:
        """Adopt a finished async audit-key load; raise while one is pending."""
        task = self._audit_load_task
        if task is None:
            return
        if not task.done():
            raise KeyManagementError(
                "Persisted audit key load is still running on the event loop; use the async audit accessor"
            )
        self._audit_load_task = None
        try:
            key_pair = task.result()
        except _OPS_ERRORS as e:
            logger.warning("Async audit key load failed: %s", e)
            return
        except asyncio.CancelledError:
            return
        if key_pair is not None:
            self._adopt_audit_key_pair(key_pair)

    def _load_persisted_audit_key(self) -> bool:
        """Best-effort load of the persisted audit keypair.

        Returns True when both halves were restored into ``_audit_key`` /
        ``_audit_private``. Sync storage paths are tried first; the async
        ``get_audit_key`` is used via ``asyncio.run`` when no loop is
        running, or scheduled on the running loop for the async accessor
        to collect (``_audit_load_task``).
        """
        key_pair = self._load_audit_key_sync()
        if isinstance(key_pair, _SyncAuditLoadUnsupported):
            key_pair = self._load_audit_key_via_async()
        if key_pair is None or isinstance(key_pair, _SyncAuditLoadUnsupported):
            return False
        return self._adopt_audit_key_pair(key_pair)

    def _load_audit_key_sync(self) -> "KeyPair | None | _SyncAuditLoadUnsupported":
        """Synchronous persisted-audit-key load.

        Returns the KeyPair, None when no persisted key exists, or the
        ``_SyncAuditLoadUnsupported`` sentinel when the backend exposes no
        working synchronous loader (caller then tries the async path).
        """
        loader = getattr(self.storage, "get_audit_key_sync", None)
        if loader is not None:
            try:
                return loader()  # type: ignore[no-any-return]
            except NotImplementedError:
                pass  # fall through to the generic pair loader
            except _OPS_ERRORS as e:
                logger.debug("Sync audit key load via get_audit_key_sync failed: %s", e)
                return None
        pair_loader = getattr(self.storage, "get_key_pair_sync", None)
        if pair_loader is not None:
            try:
                # FileKeyStorage persists the audit pair under the
                # participant id "audit" (audit.json / audit.priv).
                return pair_loader("audit")  # type: ignore[no-any-return]
            except NotImplementedError:
                pass
            except _OPS_ERRORS as e:
                logger.debug("Sync audit key load via get_key_pair_sync failed: %s", e)
                return None
        return _SYNC_AUDIT_LOAD_UNSUPPORTED

    def _load_audit_key_via_async(self) -> KeyPair | None:
        """Async persisted-audit-key load for backends without a sync path."""
        getter = getattr(self.storage, "get_audit_key", None)
        if getter is None or not asyncio.iscoroutinefunction(getter):
            return None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(getter())  # type: ignore[no-any-return]
            except _OPS_ERRORS as e:
                logger.debug("Async audit key load failed: %s", e)
                return None
        # A loop is already running and only the async getter exists: the
        # sync accessors cannot await it, so schedule the load and let
        # ``get_audit_private_key`` (or a later sync call once the task is
        # done) adopt the result via ``_settle_audit_load_task``.
        task = asyncio.ensure_future(getter())
        self._audit_load_task = task
        task.add_done_callback(self._on_audit_load_done)
        return None

    def _on_audit_load_done(self, task: "asyncio.Task[KeyPair | None]") -> None:
        """Consume a scheduled audit-key load's exception so it is not lost."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("Async audit key load failed: %s", exc)

    def _on_audit_store_done(self, task: "asyncio.Task[bool]") -> None:
        """Consume a scheduled audit-key store's result/exception."""
        if task.cancelled():
            return
        try:
            ok = task.result()
        except _OPS_ERRORS as e:
            logger.warning("Persisted audit key write failed: %s", e)
            return
        if ok is False:
            logger.warning("Persisted audit key write reported failure")

    def _adopt_audit_key_pair(self, key_pair: KeyPair) -> bool:
        """Install a persisted audit KeyPair after sanity checks.

        The private half is authoritative: the public key is re-derived
        from it and must match the stored public bytes, so a truncated or
        mismatched audit.json/audit.priv pair is rejected rather than
        adopted.
        """
        try:
            private_key = X25519PrivateKey.from_private_bytes(key_pair.private_key)
            derived_public = private_key.public_key().public_bytes_raw()
            if key_pair.public_key != derived_public:
                logger.warning("Persisted audit key public/private mismatch; ignoring it")
                return False
            self._audit_private = key_pair.private_key
            self._audit_key = private_key.public_key()
            logger.info("Loaded persisted audit key (version %s)", key_pair.version)
            return True
        except _OPS_ERRORS as e:
            logger.warning("Ignoring unusable persisted audit key: %s", e)
            return False

    def _should_rotate_audit_key(self) -> bool:
        """Check if audit key needs rotation.

        NOTE (#2162): time-based rotation (``self._audit_key_rotation``,
        currently 30 days) is NOT yet implemented — a persisted audit key
        is loaded as-is across restarts and only a missing/unusable key
        triggers regeneration. Track the key's creation time before
        enabling scheduled rotation.
        """
        return self._audit_key is None

    async def _reencrypt_transactions(self, participant_id: str, old_key_pair: KeyPair, new_key_pair: KeyPair) -> None:
        """Re-encrypt active transactions with new key

        ponytail: re-encryption requires a persistence layer for confidential
        transactions. Until that is wired and tested, the route returns 501.
        """
        logger.warning("Re-encryption not implemented for %s", participant_id)
        raise NotImplementedError("Key rotation re-encryption is not implemented")


class KeyStorageBackend:
    """Abstract base for key storage backends.

    Concrete implementations must override all methods.
    Examples: DatabaseKeyStorage, HSMKeyStorage, FileKeyStorage.
    """

    async def store_key_pair(self, key_pair: KeyPair) -> bool:
        """Store key pair securely"""
        raise NotImplementedError

    async def get_key_pair(self, participant_id: str) -> KeyPair | None:
        """Get key pair for participant"""
        raise NotImplementedError

    def get_key_pair_sync(self, participant_id: str) -> KeyPair | None:
        """Synchronous get key pair"""
        raise NotImplementedError

    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key pair"""
        raise NotImplementedError

    async def get_audit_key(self) -> KeyPair | None:
        """Get audit key pair"""
        raise NotImplementedError

    async def list_participants(self) -> list[str]:
        """List all participants"""
        raise NotImplementedError

    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke keys for participant"""
        raise NotImplementedError

    async def log_rotation(self, rotation_log: KeyRotationLog) -> bool:
        """Log key rotation"""
        raise NotImplementedError


class FileKeyStorage(KeyStorageBackend):
    """File-based key storage for development"""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(storage_path, mode=0o700, exist_ok=True)
        os.chmod(storage_path, 0o700)

    async def store_key_pair(self, key_pair: KeyPair) -> bool:
        """Store key pair to file"""
        validate_participant_id(key_pair.participant_id)
        try:
            file_path = os.path.join(self.storage_path, f"{key_pair.participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{key_pair.participant_id}.priv")
            # Create 0o600 before writing: aiofiles.open follows the umask,
            # so write-then-chmod leaves a window where the private key is
            # readable. Pre-creating with O_CREAT|0o600 keeps the mode.
            fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)  # noqa: unawaited-async - os.close is sync; the ratchet's async-shape heuristic misfires here
            os.chmod(private_path, 0o600)  # covers a pre-existing loose file
            async with aiofiles.open(private_path, "wb") as f:
                await f.write(key_pair.private_key)
            metadata = {
                "participant_id": key_pair.participant_id,
                "public_key": base64.b64encode(key_pair.public_key).decode(),
                "algorithm": key_pair.algorithm,
                "created_at": key_pair.created_at.isoformat(),
                "version": key_pair.version,
            }
            async with aiofiles.open(file_path, "w") as f:
                await f.write(json.dumps(metadata))
            return True
        except _OPS_ERRORS as e:
            logger.error("Failed to store key pair: %s", e)
            return False

    async def get_key_pair(self, participant_id: str) -> KeyPair | None:
        """Get key pair from file"""
        validate_participant_id(participant_id)
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")
            if not os.path.exists(file_path) or not os.path.exists(private_path):
                return None
            async with aiofiles.open(file_path) as f:
                metadata = json.loads(await f.read())
            async with aiofiles.open(private_path, "rb") as f:
                private_key = await f.read()
            return KeyPair(
                participant_id=metadata["participant_id"],
                private_key=private_key,
                public_key=base64.b64decode(metadata["public_key"]),
                algorithm=metadata["algorithm"],
                created_at=datetime.fromisoformat(metadata["created_at"]),
                version=metadata["version"],
            )
        except _OPS_ERRORS as e:
            logger.error("Failed to get key pair: %s", e)
            return None

    def get_key_pair_sync(self, participant_id: str) -> KeyPair | None:
        """Synchronous get key pair"""
        validate_participant_id(participant_id)
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")
            if not os.path.exists(file_path) or not os.path.exists(private_path):
                return None
            with open(file_path) as f:
                metadata = json.load(f)
            with open(private_path, "rb") as f:
                private_key = f.read()
            return KeyPair(
                participant_id=metadata["participant_id"],
                private_key=private_key,
                public_key=base64.b64decode(metadata["public_key"]),
                algorithm=metadata["algorithm"],
                created_at=datetime.fromisoformat(metadata["created_at"]),
                version=metadata["version"],
            )
        except _OPS_ERRORS as e:
            logger.error("Failed to get key pair: %s", e)
            return None

    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key"""
        audit_path = os.path.join(self.storage_path, "audit.json")
        audit_priv_path = os.path.join(self.storage_path, "audit.priv")
        try:
            fd = os.open(audit_priv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)  # noqa: unawaited-async - os.close is sync; the ratchet's async-shape heuristic misfires here
            os.chmod(audit_priv_path, 0o600)  # covers a pre-existing loose file
            async with aiofiles.open(audit_priv_path, "wb") as f:
                await f.write(key_pair.private_key)
            metadata = {
                "participant_id": "audit",
                "public_key": base64.b64encode(key_pair.public_key).decode(),
                "algorithm": key_pair.algorithm,
                "created_at": key_pair.created_at.isoformat(),
                "version": key_pair.version,
            }
            async with aiofiles.open(audit_path, "w") as f:
                await f.write(json.dumps(metadata))
            return True
        except _OPS_ERRORS as e:
            logger.error("Failed to store audit key: %s", e)
            return False

    async def get_audit_key(self) -> KeyPair | None:
        """Get audit key"""
        return self.get_key_pair_sync("audit")

    def get_audit_key_sync(self) -> KeyPair | None:
        """Synchronous audit key load (#2162 restart recovery).

        Optional sync counterpart to ``get_audit_key``; ``KeyManager``
        prefers it so persisted audit keys load without an event loop.
        """
        return self.get_key_pair_sync("audit")

    async def list_participants(self) -> list[str]:
        """List all participants"""
        # ponytail: os.listdir blocks event loop - acceptable for small directories
        participants = []
        for file in os.listdir(self.storage_path):
            if file.endswith(".json") and file != "audit.json":
                participant_id = file[:-5]
                participants.append(participant_id)
        return participants

    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke keys by deleting files"""
        validate_participant_id(participant_id)
        # ponytail: os.rename blocks event loop - acceptable for key revocation (rare operation)
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")
            revoked_path = os.path.join(self.storage_path, "revoked")
            os.makedirs(revoked_path, exist_ok=True)
            if os.path.exists(file_path):
                os.rename(file_path, os.path.join(revoked_path, f"{participant_id}.json"))  # noqa: unawaited-async — sync os.rename
            if os.path.exists(private_path):
                os.rename(private_path, os.path.join(revoked_path, f"{participant_id}.priv"))  # noqa: unawaited-async — sync os.rename
            return True
        except _OPS_ERRORS as e:
            logger.error("Failed to revoke keys: %s", e)
            return False

    async def log_rotation(self, rotation_log: KeyRotationLog) -> bool:
        """Log key rotation"""
        log_path = os.path.join(self.storage_path, "rotations.log")
        try:
            with open(log_path, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "participant_id": rotation_log.participant_id,
                            "old_version": rotation_log.old_version,
                            "new_version": rotation_log.new_version,
                            "rotated_at": rotation_log.rotated_at.isoformat(),
                            "reason": rotation_log.reason,
                        }
                    )
                    + "\n"
                )
            return True
        except _OPS_ERRORS as e:
            logger.error("Failed to log rotation: %s", e)
            return False
