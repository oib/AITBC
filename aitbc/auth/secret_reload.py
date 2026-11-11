"""In-process reload of auth secrets from env files (SECRET-RELOAD-1, #1776).

``rotate_jwt_secret.sh`` / ``rotate_api_key_secret.sh`` rewrite the shared
``/etc/aitbc/*secrets*.env`` files and then restart every consumer — the
phase-5 restart window is what breaks cross-service verification mid-rollout
(#1718). This module lets a running service re-read the secret files and swap
its in-memory secret set without a restart.

Design rules:

* **File-backed, not environ-backed.** systemd ``EnvironmentFile=`` values are
  frozen in ``os.environ`` at exec time; a reload must parse the files again.
* **Whitelist only.** Only auth-secret variables are refreshed — never chain
  config, endpoints, or unrelated secrets.
* **Fail closed.** The candidate set is fully parsed and validated before any
  value is applied; a malformed file or weak secret leaves the old set live.
* **Explicit trigger.** Call ``reload_auth_secrets()`` from a SIGHUP handler
  or admin endpoint via ``install_auth_reload_signal()``. Nothing polls.
"""

from __future__ import annotations

import os
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Variables a reload may refresh. Everything else in the env files is ignored —
# chain config, endpoints, and unrelated secrets must not mutate under a
# running process.
AUTH_SECRET_VARS = frozenset(
    {
        "JWT_SECRET",
        "JWT_SECRET_KEY",
        "JWT_SECRET_NEW",
        "JWT_SECRET_PREVIOUS",
        "JWT_ALGORITHM",
        "API_KEY_HASH_SECRET",
        "API_KEY_HASH_SECRET_NEW",
        "API_KEY_HASH_SECRET_PREVIOUS",
    }
)

_DEFAULT_ENV_FILES = ("/etc/aitbc/blockchain-secrets.env",)

_lock = threading.Lock()

# Whitelisted vars whose live value originated from a secrets env file. A var
# that disappears from the files on a later reload is removed from
# ``os.environ`` too — otherwise a completed rotation's ``*_NEW``/``*_PREVIOUS``
# overlap entries would linger forever and keep retired secrets valid.
# Vars never seen in a file (e.g. ``Environment=`` unit settings) are never
# touched.
_FILE_SOURCED: set[str] = set()


@dataclass
class ReloadReport:
    """Outcome of one reload attempt."""

    ok: bool
    applied: dict[str, str] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)


def _env_file_candidates() -> list[str]:
    """Env files to re-read, in precedence order (later wins).

    ``AITBC_AUTH_ENV_FILES`` (colon-separated) overrides the default shared
    secrets file; ``AITBC_SECRETS_ENV`` (the name update.sh already uses) is
    honored as a single-file override as well.
    """
    raw = os.getenv("AITBC_AUTH_ENV_FILES") or os.getenv("AITBC_SECRETS_ENV") or ""
    if raw:
        return [p.strip() for p in raw.split(":") if p.strip()]
    return list(_DEFAULT_ENV_FILES)


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a systemd-style env file.

    Semantics mirror ``systemd.exec``: ``KEY=VALUE`` lines, ``#`` comments,
    optional ``export`` prefix, surrounding single/double quotes stripped,
    later assignments win, missing trailing newline tolerated.
    """
    values: dict[str, str] = {}
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{lineno}: not a KEY=VALUE assignment")
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not all(c.isalnum() or c == "_" for c in key):
            raise ValueError(f"{path}:{lineno}: invalid variable name {key!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _validate_candidate(values: dict[str, str]) -> list[str]:
    """Validate the whitelisted candidate set; return error strings."""
    from aitbc.auth.jwt import _KNOWN_JWT_DEFAULTS, _validate_secret

    errors: list[str] = []
    primary = (values.get("JWT_SECRET") or values.get("JWT_SECRET_KEY") or "").strip()
    if primary:
        if len(primary) < 32:
            errors.append("JWT_SECRET is shorter than 32 characters")
        elif primary.lower() in _KNOWN_JWT_DEFAULTS:
            errors.append("JWT_SECRET is a known default value")
        else:
            try:
                _validate_secret(primary)
            except ValueError as exc:
                errors.append(f"JWT_SECRET rejected: {exc}")
    for name in ("JWT_SECRET_NEW",):
        extra = (values.get(name) or "").strip()
        if extra and len(extra) < 32:
            errors.append(f"{name} is shorter than 32 characters")
    for name in ("API_KEY_HASH_SECRET", "API_KEY_HASH_SECRET_NEW"):
        secret = (values.get(name) or "").strip()
        if secret and len(secret) < 16:
            errors.append(f"{name} is suspiciously short (<16 chars)")
    return errors


def reload_auth_secrets(env_files: list[str] | None = None) -> ReloadReport:
    """Re-read auth secret env files and swap the live secret set.

    Returns a :class:`ReloadReport`; on any parse or validation failure the
    process keeps its previous secrets (fail closed).
    """
    files = env_files if env_files is not None else _env_file_candidates()
    merged: dict[str, str] = {}
    read: list[str] = []
    errors: list[str] = []

    for raw in files:
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            merged.update(_parse_env_file(path))
            read.append(str(path))
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        return ReloadReport(ok=False, errors=errors, files_read=read)

    if not read:
        # No secrets file present — nothing to reload, leave environ alone.
        return ReloadReport(ok=True, files_read=[])

    candidates = {k: v for k, v in merged.items() if k in AUTH_SECRET_VARS}

    # A file-sourced var that vanished from every file was deliberately
    # removed (rotation phase-5 drops *_NEW / trims *_PREVIOUS) — remove it
    # from the process env too. Refuse to drop the last JWT primary.
    removals = _FILE_SOURCED - candidates.keys()
    primary_names = {"JWT_SECRET", "JWT_SECRET_KEY"}
    if removals & primary_names and not (candidates.keys() & primary_names):
        return ReloadReport(
            ok=False,
            errors=["reload would remove the last JWT primary secret"],
            files_read=read,
        )

    errors = _validate_candidate(candidates)
    if errors:
        return ReloadReport(ok=False, errors=errors, files_read=read)

    with _lock:
        applied = {k: v for k, v in candidates.items() if os.environ.get(k) != v}
        os.environ.update(candidates)
        removed = [k for k in removals if k in os.environ]
        for key in removed:
            os.environ.pop(key, None)
        if read:
            _FILE_SOURCED.clear()
            _FILE_SOURCED.update(candidates.keys())

    if applied:
        try:
            from aitbc.auth import jwt as _jwt_mod

            _jwt_mod.reload_jwt_secrets()
        except Exception:
            logger.exception("auth secret reload applied to environ but JWT refresh failed")
        logger.info(
            "auth secrets reloaded: %d updated, %d removed from %s",
            len(applied),
            len(removed),
            ", ".join(read),
        )
    else:
        logger.info("auth secrets reload: no changes (%s)", ", ".join(read) or "no files")
    return ReloadReport(ok=True, applied=applied, removed=removed, files_read=read)


def install_auth_reload_signal(signum: int = signal.SIGHUP) -> bool:
    """Install a SIGHUP (or given signal) handler that reloads auth secrets.

    Must be called from the main thread (asyncio services: call inside the
    running loop's thread before ``asyncio.run``, or from a sync startup
    hook). Returns False when the platform/signal is unavailable.
    """

    def _handler(_signum: int, _frame: Any) -> None:
        report = reload_auth_secrets()
        if not report.ok:
            logger.error("auth secret reload rejected: %s", "; ".join(report.errors))

    try:
        signal.signal(signum, _handler)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning("could not install auth-reload signal handler: %s", exc)
        return False
    logger.info("auth secret reload armed on signal %d", signum)
    return True
