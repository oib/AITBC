"""Authentication and credential management for the AITBC CLI.

This module previously kept credentials in a module-level dict. Every CLI invocation is a
separate process, so a credential "stored" in one call was gone by the next -- while
``store_credential`` reported success. It also held API keys in plaintext process memory
instead of a protected store.

Storage now uses the OS keyring when one is available. On headless hosts -- servers, CI,
containers, where this CLI mostly runs -- ``keyring`` resolves to a ``fail.Keyring``
backend whose methods raise on use, so a file-backed store under ``~/.aitbc`` (0600, owner
only) is used instead. The active backend is reported by ``backend_name`` and surfaced when
storing, because "which store holds my API key" is not something a user should have to
guess.

The file backend is deliberately not described as encrypted. The CLI's ``encode_value``
helper is base64, and calling that encoding would repeat the mistake this module is
fixing.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import cast

from ..utils import error, success, warning

_DEFAULT_STORE = Path.home() / ".aitbc" / "credentials.json"


class ExpiredAdminToken(Exception):
    """Raised when the stored admin JWT has expired."""


_JWT_SEGMENT_SEPARATOR = "."


def _jwt_payload(token: str) -> dict | None:
    """Return the payload of a JWT without verifying the signature.

    Handles base64url padding automatically. Returns ``None`` if the token is
    not a JWT or cannot be decoded.
    """
    if not token.startswith("ey") or token.count(_JWT_SEGMENT_SEPARATOR) != 2:
        return None
    try:
        payload_b64 = token.split(_JWT_SEGMENT_SEPARATOR)[1]
        padding = (4 - len(payload_b64) % 4) % 4
        payload = base64.urlsafe_b64decode(payload_b64 + "=" * padding).decode()
        return cast(dict | None, json.loads(payload))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _is_token_expired(token: str) -> bool:
    """Check whether a JWT's ``exp`` claim is in the past."""
    payload = _jwt_payload(token)
    if not payload:
        return False
    exp = payload.get("exp")
    if not isinstance(exp, int | float):
        return False
    return datetime.now(UTC).timestamp() > exp


def _resolve_keyring():
    """Return a usable keyring backend, or None.

    ``keyring`` always returns *something*; when no platform store is configured that is
    ``fail.Keyring``, whose methods raise on use. Its class is also named ``Keyring``, so
    it must be identified by type rather than by name.
    """
    try:
        import keyring
        from keyring.backends import fail as fail_backend
    except ImportError:  # pragma: no cover - depends on install extras
        return None

    try:
        backend = keyring.get_keyring()
    except Exception:  # pragma: no cover - backend discovery is platform-specific
        return None

    if isinstance(backend, fail_backend.Keyring):
        return None
    return backend


class AuthManager:
    """Manages authentication credentials, preferring the OS keyring."""

    SERVICE_NAME = "aitbc-cli"
    # Kept in sync with list_credentials' search space.
    KNOWN_ENVIRONMENTS = ("default", "dev", "staging", "prod")
    KNOWN_NAMES = ("client", "miner", "admin")

    def __init__(self, store_path: Path | None = None):
        self._keyring = _resolve_keyring()
        self._store_path = store_path or _DEFAULT_STORE

    @property
    def backend_name(self) -> str:
        """Which store is in use -- 'keyring' or 'file'."""
        return "keyring" if self._keyring is not None else "file"

    @staticmethod
    def _key(name: str, environment: str) -> str:
        return f"{environment}_{name}"

    # -- file backend -------------------------------------------------------------

    def _read_file_store(self) -> dict[str, str]:
        try:
            with open(self._store_path) as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_file_store(self, data: dict[str, str]) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        # Created 0600 directly. Writing first and chmod'ing after leaves a window in
        # which the file carries the process umask (commonly 0644) and any local user can
        # read the API keys.
        fd = os.open(self._store_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2)
        try:
            self._store_path.chmod(0o600)  # re-assert for a pre-existing file
        except OSError:  # pragma: no cover - platform dependent
            pass

    # -- public API ---------------------------------------------------------------

    def store_credential(self, name: str, api_key: str, environment: str = "default") -> bool:
        """Store an API key. Returns True on success."""
        key = self._key(name, environment)
        try:
            if self._keyring is not None:
                self._keyring.set_password(self.SERVICE_NAME, key, api_key)
            else:
                data = self._read_file_store()
                data[key] = api_key
                self._write_file_store(data)
        except Exception as exc:
            # Report it. The previous implementation always claimed success.
            error(f"Failed to store credential '{name}' for environment '{environment}': {exc}")
            return False

        if self.backend_name == "file":
            warning(f"No OS keyring available; stored in {self._store_path} (owner-readable only)")
        success(f"Credential '{name}' stored for environment '{environment}'")
        return True

    def get_credential(self, name: str, environment: str = "default", quiet: bool = False) -> str | None:
        """Retrieve an API key, or None if absent.

        ``quiet`` suppresses the not-found warning. That warning goes to
        stdout, so a caller probing for an optional credential would otherwise
        corrupt machine-readable output.
        """
        key = self._key(name, environment)
        try:
            if self._keyring is not None:
                value = self._keyring.get_password(self.SERVICE_NAME, key)
            else:
                value = self._read_file_store().get(key)
        except Exception as exc:
            error(f"Failed to read credential '{name}' for environment '{environment}': {exc}")
            return None

        if value is None and not quiet:
            warning(f"No stored credential found for '{name}' in '{environment}'")
        return cast(str | None, value)

    def get_admin_token(self, environment: str = "default") -> str | None:
        """Return the stored admin JWT if available, falling back to the client JWT.

        The token's role is a server-side claim, not a property of the storage slot,
        so an admin wallet's JWT is valid for admin routes regardless of whether it
        was stored as ``admin`` or ``client`` (the default for ``aitbc auth login``).

        Raises:
            ExpiredAdminToken: if the chosen token is a JWT whose ``exp`` claim has
            passed, so the caller can surface a friendly "run ``aitbc auth login``"
            message instead of a bare 401.
        """
        admin = self.get_credential("admin", environment, quiet=True)
        token = admin or self.get_credential("client", environment, quiet=True)
        if token and _is_token_expired(token):
            raise ExpiredAdminToken("The stored admin credential has expired. Run `aitbc auth login` to refresh it.")
        return token

    def delete_credential(self, name: str, environment: str = "default") -> bool:
        """Delete a stored API key. Returns True if one was removed."""
        key = self._key(name, environment)
        try:
            if self._keyring is not None:
                self._keyring.delete_password(self.SERVICE_NAME, key)
            else:
                data = self._read_file_store()
                if key not in data:
                    warning(f"Credential '{name}' not found for environment '{environment}'")
                    return False
                del data[key]
                self._write_file_store(data)
        except Exception:
            # keyring raises PasswordDeleteError when the entry is absent; treating that
            # as "nothing to delete" keeps the command idempotent.
            warning(f"Credential '{name}' not found for environment '{environment}'")
            return False

        success(f"Credential '{name}' deleted for environment '{environment}'")
        return True

    def list_credentials(self, environment: str | None = None) -> dict[str, str]:
        """List which known credentials are present, with values masked."""
        environments = [environment] if environment else list(self.KNOWN_ENVIRONMENTS)
        file_data = self._read_file_store() if self._keyring is None else {}
        credentials: dict[str, str] = {}

        for env in environments:
            for name in self.KNOWN_NAMES:
                key = self._key(name, env)
                try:
                    present = (
                        self._keyring.get_password(self.SERVICE_NAME, key) if self._keyring is not None else file_data.get(key)
                    )
                except Exception:  # pragma: no cover - backend-specific
                    continue
                if present:
                    credentials[f"{name}@{env}"] = "******"

        return credentials

    def store_env_credential(self, name: str) -> bool:
        """Copy an API key from the environment into the credential store."""
        env_var = f"{name.upper()}_API_KEY"
        api_key = os.getenv(env_var)
        if not api_key:
            error(f"Environment variable {env_var} not set")
            return False

        return self.store_credential(name, api_key)


__all__ = ["AuthManager", "ExpiredAdminToken"]
