"""Scratch-only reset guard for the legacy genesis/reset tooling.

The legacy destructive tools (``aitbc genesis reset``, ``unified_genesis.py``,
``create-genesis-block.py``, ``reset_chain_0x.py``, ``reset-follower-to-genesis.sh``)
were written for single-node maintenance windows: they stop systemd units,
rewrite ``/etc/aitbc/*.env``, and rebuild ``/var/lib/aitbc/data/...``.  On the
current multi-proposer fleet those paths are live state, so every guarded tool
refuses unless the operator has opted in to a scratch run by exporting
``AITBC_RESET_SCRATCH=<absolute path>`` — and even then every declared target
must resolve under that root.

There is deliberately **no live override**.  The reset-day write on the live
hosts is the job of the new genesis builder (``aitbc_chain.genesis_builder`` /
``scripts/ops/build-genesis.py``), which has its own refusals.

Checks, in order:

1. **Scratch marker** — ``AITBC_RESET_SCRATCH`` must be set to an absolute
   path outside the live prefixes.
2. **Target confinement** — every declared target resolves under the scratch
   root and never under ``/var/lib/aitbc``, ``/etc/aitbc``, or ``/root``.
   Reads (env files, keystore, service-account keystore) are confined the same
   way: a scratch run must never read a live keystore or env file.
3. **Live chain-id** — the target chain id must differ from every ``CHAIN_ID``
   found in the live ``/etc/aitbc/*.env`` files and from every chain directory
   under the live data dir.
4. **Multi-proposer** — tools that rewrite validator identity refuse when the
   target env's ``VALIDATOR_SET`` already parses to more than one entry; the
   legacy writers can only emit a single-proposer set and would silently
   collapse a multi-proposer one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCRATCH_ENV = "AITBC_RESET_SCRATCH"

LIVE_ETC_DIR = Path("/etc/aitbc")
LIVE_DATA_DIR = Path("/var/lib/aitbc")
LIVE_ROOT_DIR = Path("/root")
LIVE_PREFIXES = (LIVE_DATA_DIR, LIVE_ETC_DIR, LIVE_ROOT_DIR)


class ResetGuardError(RuntimeError):
    """Raised when a destructive tool is invoked outside a scratch context."""


def scratch_root(environ: dict[str, str] | None = None) -> Path:
    """Return the resolved scratch root, raising unless the marker is set."""
    env = os.environ if environ is None else environ
    raw = env.get(SCRATCH_ENV, "").strip()
    if not raw:
        raise ResetGuardError(
            f"{SCRATCH_ENV} is not set — refusing to run a destructive reset "
            "tool outside a declared scratch root. These legacy tools no "
            "longer have a live mode; reset-day writes go through "
            "scripts/ops/build-genesis.py."
        )
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ResetGuardError(f"{SCRATCH_ENV} must be an absolute path: {raw}")
    resolved = root.resolve()
    for prefix in LIVE_PREFIXES:
        if resolved == prefix or prefix in resolved.parents:
            raise ResetGuardError(
                f"{SCRATCH_ENV}={resolved} is inside live path {prefix} — "
                "the scratch root must be a fresh directory away from the "
                "live layout."
            )
    return resolved


def _resolve(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def assert_scratch_targets(*targets: Path | str, environ: dict[str, str] | None = None) -> Path:
    """Every target must resolve under the scratch root and outside live paths.

    Returns the scratch root for callers that want to derive more paths from it.
    """
    root = scratch_root(environ)
    for target in targets:
        resolved = _resolve(target)
        for prefix in LIVE_PREFIXES:
            if _under(resolved, prefix):
                raise ResetGuardError(
                    f"reset-guard: target {target} resolves to {resolved}, inside live path {prefix} — refusing."
                )
        if not _under(resolved, root):
            raise ResetGuardError(
                f"reset-guard: target {target} resolves to {resolved}, outside scratch root {root} — refusing."
            )
    return root


def assert_data_dir_env(environ: dict[str, str] | None = None) -> Path:
    """AITBC_DATA_DIR (the node library's write root) must be scratch-confined.

    Tools that call into ``aitbc_chain.database.init_db`` write under the
    settings data dir, which defaults to ``/var/lib/aitbc/data`` — a hidden
    live write unless the caller has pointed ``AITBC_DATA_DIR`` at the scratch
    root as well.
    """
    env = os.environ if environ is None else environ
    data_dir = Path(env.get("AITBC_DATA_DIR", str(LIVE_DATA_DIR)))
    try:
        return assert_scratch_targets(data_dir, environ=environ)
    except ResetGuardError as exc:
        raise ResetGuardError(
            f"AITBC_DATA_DIR must point at a directory under the scratch root (resolves to {data_dir}): {exc}"
        ) from exc


def _env_files(etc_dir: Path) -> list[Path]:
    try:
        return sorted(etc_dir.glob("*.env"))
    except OSError:
        return []


def _chain_ids_in_envs(etc_dir: Path) -> set[str]:
    ids: set[str] = set()
    for env_file in _env_files(etc_dir):
        try:
            for line in env_file.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("CHAIN_ID="):
                    value = stripped.partition("=")[2].strip().strip('"').strip("'")
                    if value:
                        ids.add(value)
        except OSError:
            continue
    return ids


def _chain_ids_in_data_dir(data_dir: Path) -> set[str]:
    ids: set[str] = set()
    try:
        for child in data_dir.iterdir():
            if child.is_dir():
                ids.add(child.name)
    except OSError:
        pass
    return ids


def live_chain_ids(etc_dir: Path | None = None, data_dir: Path | None = None) -> set[str]:
    """Chain ids observed in the live layout (read-only probe)."""
    return _chain_ids_in_envs(etc_dir or LIVE_ETC_DIR) | _chain_ids_in_data_dir(data_dir or (LIVE_DATA_DIR / "data"))


def assert_not_live_chain(
    chain_id: str,
    *,
    etc_dir: Path | None = None,
    data_dir: Path | None = None,
) -> None:
    live = live_chain_ids(etc_dir, data_dir)
    if chain_id in live:
        raise ResetGuardError(
            f"reset-guard: target chain_id {chain_id!r} is a live chain id "
            f"(found in {etc_dir or LIVE_ETC_DIR}/ or under "
            f"{data_dir or (LIVE_DATA_DIR / 'data')}/) — refusing."
        )


def validator_set_size(etc_dir: Path) -> int | None:
    """Entries in the target env's VALIDATOR_SET, or None when unset/unparseable."""
    for env_file in _env_files(etc_dir):
        try:
            for line in env_file.read_text().splitlines():
                stripped = line.strip()
                if not stripped.startswith("VALIDATOR_SET="):
                    continue
                value = stripped.partition("=")[2].strip().strip('"').strip("'")
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return None
                if isinstance(parsed, list):
                    return len(parsed)
                return None
        except OSError:
            continue
    return None


def assert_single_proposer(etc_dir: Path | str) -> None:
    """Refuse when the target env already carries a multi-proposer validator set.

    The legacy writers collapse VALIDATOR_SET to one proposer; refusing here
    keeps them from silently degrading a multi-proposer set.
    """
    size = validator_set_size(Path(etc_dir))
    if size is not None and size > 1:
        raise ResetGuardError(
            f"reset-guard: target env in {etc_dir} has VALIDATOR_SET with "
            f"{size} proposers — this tool can only write a single-proposer "
            "set and refusing beats silently collapsing it."
        )
