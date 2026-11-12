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
import re
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

# #1852: service-scoped JWT secrets are dynamic names
# (``JWT_SECRET_<SCOPE>``, ``JWT_SECRET_<SCOPE>_NEW``/``_PREVIOUS``) — the
# frozenset above cannot enumerate them, so the whitelist also accepts any
# ``JWT_SECRET``/``API_KEY_HASH_SECRET`` name built from env-safe segments.
_AUTH_SECRET_VAR_RE = re.compile(r"^(?:JWT_SECRET|API_KEY_HASH_SECRET)(?:_[A-Z0-9]+)*$")


def _is_auth_secret_var(name: str) -> bool:
    """Whitelist check: base names plus service-scoped ``*_SECRET_<SCOPE>*``."""
    return name in AUTH_SECRET_VARS or bool(_AUTH_SECRET_VAR_RE.match(name))


def _is_jwt_primary_name(name: str) -> bool:
    """A JWT signing secret (not a rotation overlap entry)."""
    return name.startswith("JWT_SECRET") and not name.endswith(("_NEW", "_PREVIOUS"))


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
    from aitbc.auth.jwt import _validate_secret

    errors: list[str] = []
    for name, raw_secret in sorted(values.items()):
        secret = (raw_secret or "").strip()
        if not secret:
            continue
        if name.startswith("JWT_SECRET"):
            if name.endswith("_PREVIOUS"):
                continue  # comma-separated retired list — same as before
            try:
                _validate_secret(secret)
            except ValueError as exc:
                errors.append(f"{name} rejected: {exc}")
        elif name.startswith("API_KEY_HASH_SECRET") and not name.endswith("_PREVIOUS") and len(secret) < 16:
            errors.append(f"{name} is suspiciously short (<16 chars)")
    return errors


def _collect_env_values(files: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    """Merge whitelisted candidates across env files (later files win)."""
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
    return merged, read, errors


def _plan_removals(candidates: dict[str, str]) -> tuple[list[str], str | None]:
    """Vars to drop because they vanished from the files; error if JWT primary lost."""
    removals = _FILE_SOURCED - candidates.keys()
    jwt_primaries = {n for n in _FILE_SOURCED | candidates.keys() if _is_jwt_primary_name(n)}
    if removals & jwt_primaries and not (candidates.keys() & jwt_primaries):
        return [], "reload would remove the last JWT primary secret"
    return sorted(removals), None


def _apply_candidates(candidates: dict[str, str], removals: list[str]) -> tuple[dict[str, str], list[str]]:
    """Swap environ values; returns (applied, actually-removed)."""
    applied = {k: v for k, v in candidates.items() if os.environ.get(k) != v}
    os.environ.update(candidates)
    removed = [k for k in removals if k in os.environ]
    for key in removed:
        os.environ.pop(key, None)
    return applied, removed


def reload_auth_secrets(env_files: list[str] | None = None) -> ReloadReport:
    """Re-read auth secret env files and swap the live secret set.

    Returns a :class:`ReloadReport`; on any parse or validation failure the
    process keeps its previous secrets (fail closed).
    """
    files = env_files if env_files is not None else _env_file_candidates()
    merged, read, errors = _collect_env_values(files)
    if errors:
        return ReloadReport(ok=False, errors=errors, files_read=read)
    if not read:
        # No secrets file present — nothing to reload, leave environ alone.
        return ReloadReport(ok=True, files_read=[])

    candidates = {k: v for k, v in merged.items() if _is_auth_secret_var(k)}
    removals, plan_error = _plan_removals(candidates)
    if plan_error:
        return ReloadReport(ok=False, errors=[plan_error], files_read=read)

    errors = _validate_candidate(candidates)
    if errors:
        return ReloadReport(ok=False, errors=errors, files_read=read)

    with _lock:
        applied, removed = _apply_candidates(candidates, removals)
        _FILE_SOURCED.clear()
        _FILE_SOURCED.update(candidates.keys())

    if applied or removed:
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
        logger.info("auth secrets reload: no changes (%s)", ", ".join(read))
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
