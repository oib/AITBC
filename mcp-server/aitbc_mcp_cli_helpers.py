"""AITBC CLI command-string helpers for the MCP server (split from aitbc_mcp_server, #1860).

Command construction (``_build_aitbc_cli_command`` and its option/path
token helpers), the destructive/read-only subcommand classification tables,
and the ``env`` prefix renderer live here.  ``aitbc_mcp_server`` re-exports
every name so existing ``from aitbc_mcp_server import ...`` call sites and
tests keep working unchanged.

This module deliberately has **no** dependency on ``aitbc_mcp_server``: the
``aitbc`` CLI path resolution (``_aitbc_cli_path`` / ``AITBC_CLI``) lives here
too, and the server re-exports it, so ``import aitbc_mcp_cli_helpers`` works
standalone in either import order.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

from aitbc_mcp_cli_tools_generated_groups import (
    GENERATED_AITBC_GROUPS,
    GENERATED_DESTRUCTIVE_AITBC_PATHS,
    GENERATED_READ_ONLY_AITBC_PATHS,
)


def _aitbc_cli_path() -> str:
    """Resolve the path to the ``aitbc`` CLI executable.

    Order of preference:
    1. ``AITBC_MCP_AITBC_CLI`` environment variable.
    2. ``aitbc`` on ``$PATH`` (respects active venv / poetry shell).
    3. ``<sys.prefix>/bin/aitbc`` (the current virtual environment).
    4. The legacy hard-coded ``/opt/aitbc/venv/bin/aitbc``.
    """
    env_path = os.getenv("AITBC_MCP_AITBC_CLI", "").strip()
    if env_path:
        return env_path

    from_path = shutil.which("aitbc")
    if from_path:
        return from_path

    venv_path = Path(sys.prefix) / "bin" / "aitbc"
    if venv_path.is_file():
        return str(venv_path)

    return "/opt/aitbc/venv/bin/aitbc"


# Backwards-compatible constant for modules that import the name directly.
# ``aitbc_mcp_server`` re-exports this name unchanged.
AITBC_CLI = _aitbc_cli_path()


def _build_env_prefix(env: dict[str, str] | None) -> str:
    """Build a shell-safe environment-variable prefix for a remote command."""
    if not env:
        return ""
    parts: list[str] = []
    for key, value in env.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"invalid environment variable name: {key}")
        parts.append(f"{key}={shlex.quote(value)}")
    return " ".join(parts) + " " if parts else ""


# ---------------------------------------------------------------------------
# AITBC CLI pivot helpers
# ---------------------------------------------------------------------------

# Top-level aitbc CLI groups the generic ``run_aitbc_cli`` / ``read_aitbc_cli``
# / ``list_aitbc_cli_group`` pivots may target.  ``GENERATED_AITBC_GROUPS`` is
# emitted by ``scripts/dev/generate_mcp_cli_tools.py --split-by-group`` next to
# the per-group tool modules, so the allow-list can never drift behind the set
# of groups that actually have generated MCP tools (SM-06 / MCP-GROUPS-1: ten
# groups, including ``dispute`` and ``energy``, were registered as tools but
# rejected by this gate).  Which commands get tools — and therefore which
# groups land here — stays a policy decision in this generator's
# FORCE_SKIP/FORCE_DESTRUCTIVE lists, not in this set.
#
# ``_CURATED_ONLY_AITBC_GROUPS`` covers real CLI groups whose tools are all
# hand-written and therefore have no generated module: ``update`` is a bare
# top-level command wrapped by the curated ``aitbc_update`` tool in
# ``aitbc_mcp_cli_tools.py``.
_CURATED_ONLY_AITBC_GROUPS = frozenset({"update"})
ALL_AITBC_GROUPS = GENERATED_AITBC_GROUPS | _CURATED_ONLY_AITBC_GROUPS

# Subcommands that are known to mutate state.  The generic ``run_aitbc_cli``
# tool treats these as destructive and requires dry_run=false and confirm=true.
DESTRUCTIVE_AITBC_SUBCOMMANDS = {
    "submit",
    "cancel",
    "refund",
    "accept",
    "create",
    "delete",
    "send",
    "spend",
    "stake",
    "unstake",
    "fund",
    "import-wallet",
    "restore",
    "backup",
    "propose",
    "vote",
    "execute",
    "start",
    "stop",
    "restart",
    "offer",
    "process",
    "run",
    "transcribe",
    "buy",
    "sell",
    "trade",
    "order",
    "deposit",
    "withdraw",
    "deploy",
    "update",
    "multisig-propose",
    "multisig-sign",
    "liquidity-stake",
    "liquidity-unstake",
    "rate",
    "publish",
    "register",
    "unregister",
    "bind",
    "escrow",
    "appeal",
    "lock",
    "release",
    "slash",
    "top-up",
    "batch",
    "login",
    "logout",
    "mint-ait",
    "withdraw-eth",
    "sync-ratings",
    "offer-disable",
    # TOOL-1 audit (walked the full Click tree at 895a738a9 and read the
    # handlers): leaf names below were verified to POST/PUT/DELETE, write a
    # file, sign or broadcast.  Matching is exact per path token, so compound
    # names like ``set-payout`` need their whole token here.
    "add",
    "add-liquidity",
    "aggregate-votes",
    "allocate",
    "approve",
    "attest",
    "authorize",
    "auto-adjudicate",
    "bootstrap-env",
    "call",
    "cancel-request",
    "close",
    "config-export",
    "config-import",
    "config-set",
    "confirm",
    "create-pair",
    "create-profile",
    "create-workflow",
    "deallocate",
    "delegate",
    "delete-db",
    "delete-metric",
    "deploy-brand",
    "eth-send",
    "deposit-eth",
    "deregister",
    "disburse",
    "download",
    "earn",
    "edit",
    "env-set",
    "execute-cross-chain",
    "export-audit",
    "feedback",
    "force-sync",
    "harden",
    "heartbeat",
    "hermes",
    "hire",
    "host",
    "import-config",
    "ingest-header",
    "init",
    "init-db",
    "init-platform",
    "join",
    "keygen",
    "launch",
    "leave",
    # MSG-2 signed forum actions (sign + broadcast a MESSAGE tx).
    "hide",
    "unhide",
    "mod-grant",
    "mod-revoke",
    "liquidity-claim",
    "load",
    "lock-escrow",
    "match-all",
    "message",
    "migrate",
    "multisig-create",
    "offer-cancel",
    "optimize",
    "patch",
    "pay",
    "ping",
    "pin",
    "policy",
    "power",
    "process-video",
    "proof",
    "propagate",
    "proposal",
    "quote",
    "rebalance",
    "reconcile",
    "record",
    "refund-sweep",
    "register-chain",
    "register-identity",
    "register-validator",
    "reject",
    "rekey",
    "remove",
    "remove-gpu",
    "reopen",
    "request",
    "request-coins",
    "reset",
    "resolve",
    "run-script",
    "save",
    "scan-gpus",
    "set",
    "set-payout",
    "set-secret",
    "set-sync-source",
    "settle",
    "sign-proof",
    "start-trading",
    "store",
    "store-header",
    "submit-job",
    "submit-request",
    "subscribe",
    "swap",
    "sweep",
    "swarm-key",
    "switch",
    "sync",
    "sync-db",
    "sync-from-hub",
    "transfer",
    "unlock",
    "unpin",
    "unset",
    "upload",
    "webhooks",
}

# Full ``group subpath`` entries whose leaf name is shared with a read-only
# command, so token matching alone would over-gate (e.g. ``trade match``
# mutates while ``market match`` is a read).  Also covers bare top-level
# mutating commands like ``aitbc start`` whose subcommand list is empty and
# so can never match a token.
DESTRUCTIVE_AITBC_PATHS = {
    "bond lock-onchain",
    "ai service test",
    "contract verify",
    "crosschain bridge",
    "dispute file",
    "edge island bridge",
    "liquidity-stake",
    "monitor alerts",
    "monitor webhooks",
    "restart",
    "stake",
    "start",
    "stop",
    "sync bulk",
    "trade match",
    "unstake",
    "update",
    "wallet export",
}


def _safe_option_key(key: str) -> bool:
    """Validate a CLI option name: only letters, digits, dashes and underscores."""
    return bool(re.match(r"^[A-Za-z0-9_-]+$", key))


def _append_cli_option_tokens(tokens: list[str], options: dict[str, Any]) -> None:
    """Append ``--key`` / ``--key=value`` tokens for a Click option mapping."""
    for key, value in options.items():
        if not _safe_option_key(key):
            raise ValueError(f"invalid option key: {key}")
        if isinstance(value, list):
            for v in value:
                if v is None or v == "":
                    tokens.append(f"--{key}")
                else:
                    tokens.append(f"--{key}={shlex.quote(str(v))}")
        elif value is None or value == "":
            tokens.append(f"--{key}")
        else:
            tokens.append(f"--{key}={shlex.quote(str(value))}")


def _collect_options(
    scope: dict[str, Any],
    flags: dict[str, str],
    values: dict[str, str],
    dual_flags: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Collect CLI options from a generated tool's local scope.

    ``scope`` is the caller's ``locals()`` mapping parameter names to values.
    ``flags`` maps boolean-flag parameter names to CLI option names: a truthy
    value emits the bare ``--flag`` (recorded as ``None``). ``values`` maps
    value-option parameter names to CLI option names: any non-``None`` value is
    recorded for ``--flag=value``. ``dual_flags`` maps a tri-state boolean
    parameter to its ``(positive, negative)`` CLI spellings for dual flag pairs
    like ``--wait``/``--no-wait``: ``True`` emits ``--positive``, ``False``
    emits ``--negative`` and ``None`` emits nothing.
    """
    options: dict[str, Any] = {}
    for name, flag in flags.items():
        if scope.get(name):
            options[flag] = None
    for name, pair in (dual_flags or {}).items():
        value = scope.get(name)
        if value is None:
            continue
        options[pair[0] if value else pair[1]] = None
    for name, flag in values.items():
        if scope.get(name) is not None:
            options[flag] = scope[name]
    return options


def _build_aitbc_cli_command(
    group: str,
    subcommand: str | list[str] | None = None,
    args: list[str] | None = None,
    options: dict[str, Any] | None = None,
    output_format: str = "json",
    *,
    group_options: dict[str, Any] | None = None,
    subcommand_options: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str:
    """Build a quoted aitbc CLI command string.

    Global options like ``--output`` are placed before the group. Group-specific
    options are placed after the group but before the subcommand to match how
    Click parses them, e.g.::

        aitbc --output json wallet --wallet-name genesis balance

    For backward compatibility the ``options`` parameter is treated as an alias
    for ``subcommand_options``.

    ``env``/``cwd`` are rendered as POSIX prefixes in the returned string
    (``cd <dir> && KEY=value <command>``) which the remote login shell
    interprets; the local branch of :func:`_run_remote` peels them back off
    into real ``env``/``cwd`` child settings.
    """
    tokens: list[str] = [AITBC_CLI]
    if output_format in {"json", "yaml", "csv"}:
        tokens.append(f"--output={output_format}")
    tokens.append(shlex.quote(group))

    # Group-level options must appear before any subcommand.
    _append_cli_option_tokens(tokens, group_options or {})

    for token in _subcommand_tokens(subcommand):
        tokens.append(shlex.quote(str(token)))

    for arg in args or []:
        tokens.append(shlex.quote(str(arg)))

    # Subcommand-level options appear after positional arguments.
    _append_cli_option_tokens(tokens, subcommand_options or options or {})

    command = _build_env_prefix(env) + " ".join(tokens)
    if cwd:
        command = f"cd {shlex.quote(cwd)} && " + command
    return command


def _subcommand_tokens(subcommand: str | list[str] | None) -> list[str]:
    """Normalise a subcommand to its path tokens.

    A string containing whitespace is split with ``shlex.split`` so
    ``"bridge sell lock"`` and ``["bridge", "sell", "lock"]`` classify
    identically — and a multi-word string cannot bypass the per-token
    destructive check.
    """
    if not subcommand:
        return []
    if isinstance(subcommand, str):
        return shlex.split(subcommand)
    return [str(token) for token in subcommand]


# Destructive paths as token tuples for prefix matching.  Every entry is a
# leaf command (verified against the Click tree), so any longer token path can
# only be positional-argument spellings of the same mutating leaf — e.g.
# ``monitor alerts remove`` — never a deeper read subcommand.
_DESTRUCTIVE_PATH_TOKENS = tuple(tuple(path.split()) for path in DESTRUCTIVE_AITBC_PATHS)


def _split_path_tokens(elements: list[str]) -> list[str]:
    """Flatten path elements, splitting embedded whitespace per element.

    ``["alerts", "list"]``, ``["alerts list"]`` and the string ``"alerts
    list"`` must classify identically — a token-splitting difference must not
    bypass the gate (SM-05).  An element that fails ``shlex.split`` (unbalanced
    quote) is kept as one token.
    """
    tokens: list[str] = []
    for el in elements:
        try:
            parts = shlex.split(el)
        except ValueError:
            parts = [el]
        tokens.extend(parts or [el])
    return tokens


_READ_ONLY_PATH_TOKENS = {tuple(p.split()) for p in GENERATED_READ_ONLY_AITBC_PATHS}
_GENERATED_DESTRUCTIVE_PATH_TOKENS = {tuple(p.split()) for p in GENERATED_DESTRUCTIVE_AITBC_PATHS}


def _is_aitbc_subcommand_read_only(
    subcommand: str | list[str] | None,
    group: str | None = None,
    args: list[str] | None = None,
) -> bool:
    """True when the effective command path is covered by a typed read tool.

    The effective path is ``group + subcommand tokens + positional args``
    (same construction as the destructive check). A read-only generated path
    must be a *prefix* of it: trailing tokens are positional arguments the
    read command itself takes. Anything a typed read tool does not cover is
    not presumed safe — unknown leaves are refused at read_aitbc_cli and can
    still run through run_aitbc_cli with the usual confirm (#849).
    """
    tokens = _split_path_tokens([str(t) for t in _subcommand_tokens(subcommand)] + [str(a) for a in (args or [])])
    path = tuple([str(group).lower()] if group else []) + tuple(token.lower() for token in tokens)
    if not path:
        return False
    best = max((len(rp) for rp in _READ_ONLY_PATH_TOKENS if path[: len(rp)] == rp), default=0)
    if not best:
        return False
    # A destructive generated command nested under a read path (e.g. 'agent
    # discover agents' below read 'agent discover') must not inherit the read
    # verdict — the deeper generated prefix wins over positional-arg fallback.
    return not any(path[: len(dp)] == dp and len(dp) > best for dp in _GENERATED_DESTRUCTIVE_PATH_TOKENS)


def _is_aitbc_subcommand_destructive(
    subcommand: str | list[str] | None,
    group: str | None = None,
    args: list[str] | None = None,
) -> bool:
    """Return True when the effective command path is known to mutate state.

    The effective path is ``group + subcommand tokens + positional args``:
    Click consumes leading positionals as further path tokens, so ``args`` can
    continue — or, when ``subcommand`` is None/empty, wholly supply — the
    command path (``args=["alerts", "remove"]`` runs ``monitor alerts
    remove``).  Both the per-token set and the path set are checked over the
    full effective path; path entries match as a token prefix, so deeper
    spellings of a destructive leaf (``monitor alerts test``) cannot escape.

    Trade-off: a positional *argument* equal to a destructive word (e.g. a
    resource literally named ``send``) over-gates the read — it is refused
    here and can still run via ``run_aitbc_cli`` with ``confirm=true``.  For a
    safety gate that direction is correct; ids in practice are hex/numeric.
    """
    tokens = _split_path_tokens([str(t) for t in _subcommand_tokens(subcommand)] + [str(a) for a in (args or [])])
    # The group token itself is never scanned: ``trade`` is a group name *and*
    # a destructive leaf elsewhere, and scanning it would gate every read in
    # that group.
    if any(token.lower() in DESTRUCTIVE_AITBC_SUBCOMMANDS for token in tokens):
        return True
    path = ([str(group).lower()] if group else []) + [token.lower() for token in tokens]
    if not path:
        return False
    return any(path[: len(dp)] == list(dp) for dp in _DESTRUCTIVE_PATH_TOKENS)


def _option_key_suggests_mutation(key: str) -> bool:
    """Best-effort scan of an option name for mutating verbs (MCP-GATE-1).

    Option *names* are flag spellings, so a read-looking path can still carry
    a mutating flag (``--set``, ``--force``, ``--send`` ...). Matching is
    exact against the destructive verb set — hyphenated names like
    ``min-reputation`` never equal a bare verb. This is a heuristic, not a
    proof: a mutation behind an innocuous flag name still needs the path
    allowlist to catch it, which is why the no-confirm path below is
    allowlist-based in the first place.
    """
    normalized = key.strip().lower().lstrip("-")
    return normalized in DESTRUCTIVE_AITBC_SUBCOMMANDS


def _options_suggest_mutation(*option_maps: dict[str, Any] | None) -> bool:
    for option_map in option_maps:
        for key in option_map or {}:
            if _option_key_suggests_mutation(str(key)):
                return True
    return False
