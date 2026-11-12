#!/usr/bin/env python3
"""AITBC Model Context Protocol (MCP) server.

Exposes tools for operating AITBC nodes over SSH on the live AITBC hosts.
Role-to-host mapping is loaded from an external config file or environment
variable; it is not hardcoded in this file.  Capabilities are intentionally
safe by default:

* Read-only inspection tools use ``ToolAnnotations(read_only_hint=True)``.
* Destructive tools default to ``dry_run=True`` and additionally require
  ``confirm=True`` before they actually execute a command on a remote host.

Environment variables
---------------------
AITBC_MCP_HOSTS         JSON string with role/host mapping.
AITBC_MCP_HOSTS_FILE    Path to a JSON/YAML hosts config file.
AITBC_MCP_SSH_USER      SSH user for remote hosts (default: current user).
AITBC_MCP_DEFAULT_HOST  Fallback host when no role is given.
AITBC_MCP_LOG_LEVEL     Server log level (default: INFO).

The server speaks stdio MCP transport, which is what Devin CLI expects for a
local command-based MCP server.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from aitbc_mcp_cli_tools_generated_groups import (
    GENERATED_AITBC_GROUPS,
    GENERATED_DESTRUCTIVE_AITBC_PATHS,
    GENERATED_READ_ONLY_AITBC_PATHS,
)
from aitbc_mcp_mask import mask_envelope

mcp = MCPServer("aitbc", log_level=os.getenv("AITBC_MCP_LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NodeRole = Literal["hub", "customer", "shop", "follower", "customer2", "follower2"]

LOCAL_MODE = os.getenv("AITBC_MCP_LOCAL", "").lower() in {"1", "true", "yes", "on"}

# Cache for the external role/host configuration.
_HOSTS_CONFIG: dict[str, Any] | None = None

# Candidate paths for the optional external hosts configuration. Network
# topology (role -> host, default host, ssh user) is intentionally kept out of
# the repository; the operator supplies it via env var or one of these files.
_HOSTS_CONFIG_PATHS = [
    Path(os.getenv("AITBC_MCP_HOSTS_FILE", "")),
    Path.home() / ".aitbc" / "mcp-hosts.yaml",
    Path.home() / ".aitbc" / "mcp-hosts.json",
    Path("/etc/aitbc/mcp-hosts.yaml"),
    Path("/etc/aitbc/mcp-hosts.json"),
]


def _load_hosts_config() -> dict[str, Any]:
    """Load role/host mapping from an external config file or env var.

    Search order:
    1. ``AITBC_MCP_HOSTS`` environment variable (JSON string).
    2. ``AITBC_MCP_HOSTS_FILE`` environment variable (path to JSON/YAML file).
    3. ``~/.aitbc/mcp-hosts.{yaml,json}``
    4. ``/etc/aitbc/mcp-hosts.{yaml,json}``

    Expected format (JSON or YAML):

    .. code-block:: yaml

        ssh_user: oib
        default_host: hub.example
        roles:
          hub: hub.example
          customer: node0.example
          shop: shop.example
          follower: shop.example
          customer2: hub1.example
          follower2: hub1.example
    """
    global _HOSTS_CONFIG
    if _HOSTS_CONFIG is not None:
        return _HOSTS_CONFIG

    config: dict[str, Any] = {}
    env_hosts = os.getenv("AITBC_MCP_HOSTS", "").strip()
    if env_hosts:
        try:
            config = json.loads(env_hosts)
        except json.JSONDecodeError as e:
            raise ValueError(f"AITBC_MCP_HOSTS is not valid JSON: {e}") from e
    else:
        for path in _HOSTS_CONFIG_PATHS:
            if not path or not path.name:
                continue
            try:
                if not path.is_file():
                    continue
                with path.open("r", encoding="utf-8") as f:
                    if path.suffix in (".yaml", ".yml"):
                        try:
                            import yaml
                        except ImportError:
                            continue
                        data = yaml.safe_load(f)
                    else:
                        data = json.load(f)
                if data:
                    config = data
                    break
            except Exception as e:
                sys.stderr.write(f"warning: could not load MCP hosts config from {path}: {e}\n")

    config.setdefault("roles", {})
    config.setdefault("default_host", os.getenv("AITBC_MCP_DEFAULT_HOST", ""))
    config.setdefault("ssh_user", os.getenv("AITBC_MCP_SSH_USER", ""))

    _HOSTS_CONFIG = config
    return config


def _role_hosts() -> dict[str, str]:
    """Return the role -> host mapping from the external configuration."""
    return _load_hosts_config().get("roles", {})


def _default_host() -> str:
    """Return the default host from the external configuration."""
    return _load_hosts_config().get("default_host", "")


def _ssh_user() -> str:
    """Return the SSH user from the external configuration."""
    return _load_hosts_config().get("ssh_user", "")


# Friendly site labels for the well-known roles in list_nodes. These are not
# network info and do not change host resolution.
_ROLE_SITES = {
    "hub": "hub/proposer node",
    "customer": "customer node",
    "customer2": "customer replica",
    "shop": "shop/follower node",
    "follower": "shop/follower node",
    "follower2": "follower/customer replica",
}

# Base SSH options: no interactive prompts, time out quickly. Host-key checking is
# handled per-host by _ssh_opts; new keys are never silently accepted unless the
# operator explicitly disables strict host-key checking.
SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
]


def _known_hosts_file(host: str) -> Path | None:
    """Return the known_hosts file to use for ``host``.

    Resolution order:
    1. ``AITBC_MCP_SSH_KNOWN_HOSTS`` environment variable.
    2. ``known_hosts`` in the loaded hosts config (global or per-role).
    3. ``~/.ssh/known_hosts`` if it exists.
    4. ``/etc/ssh/ssh_known_hosts`` if it exists.

    Returns None when no known-hosts file can be located; callers should refuse the
    connection in strict mode rather than falling back to accept-new.
    """
    env_path = os.getenv("AITBC_MCP_SSH_KNOWN_HOSTS", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        return path if path.is_file() else None

    config = _load_hosts_config()
    roles = config.get("roles", {})
    role = _role_for_host(host)
    for key in (f"known_hosts_{role}", "known_hosts"):
        value = config.get(key)
        if value:
            path = Path(str(value)).expanduser()
            return path if path.is_file() else None
    for role_key, role_host in roles.items():
        if role_host == host and role_key:
            value = config.get(f"known_hosts_{role_key}")
            if value:
                path = Path(str(value)).expanduser()
                return path if path.is_file() else None

    candidates = [Path.home() / ".ssh" / "known_hosts", Path("/etc/ssh/ssh_known_hosts")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _ssh_strict() -> bool:
    """Return True unless the operator explicitly opts out of strict host-key checks."""
    return os.getenv("AITBC_MCP_SSH_STRICT", "true").lower() not in {"0", "false", "no", "off"}


# How long an idle multiplexed master stays up after the last session closes,
# so back-to-back tool calls keep reusing it without pinning it forever.
SSH_MUX_PERSIST = "10m"


def _ssh_mux_enabled() -> bool:
    """Return True unless the operator explicitly opts out of ssh connection reuse."""
    return os.getenv("AITBC_SSH_MUX", "1").lower() not in {"0", "false", "no", "off"}


def _ssh_mux_opts() -> list[str]:
    """ControlMaster/ControlPersist options so repeat calls share one session.

    ``ControlMaster=auto`` lets the first call to a host become the master and
    later calls ride the same TCP connection over a control socket, skipping
    the per-call handshake (and the PAM/systemd session each side would
    otherwise create). ``%C`` hashes the full connection tuple, so distinct
    user/host/port/jump combinations get distinct sockets in a short,
    unix-path-safe name. Stale sockets are handled by ssh itself: ``auto``
    replaces a dead master. Set ``AITBC_SSH_MUX=0`` to return to one
    connection per call.
    """
    if not _ssh_mux_enabled():
        return []
    control_path = Path.home() / ".ssh" / "aitbc-mcp-%C"
    return [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPersist={SSH_MUX_PERSIST}",
        "-o",
        f"ControlPath={control_path}",
    ]


def _ssh_opts(host: str) -> list[str]:
    """Build SSH options for ``host`` using a managed known_hosts file.

    If strict host-key checking is enabled (default) and no known_hosts file is
    available, the returned options will cause the connection to fail instead of
    silently trusting a new key. Set ``AITBC_MCP_SSH_STRICT=false`` to re-enable
    the legacy ``accept-new`` behaviour only for bring-up/testing.
    """
    opts = list(SSH_OPTS)
    known_hosts = _known_hosts_file(host)
    if known_hosts:
        opts.extend(["-o", f"UserKnownHostsFile={known_hosts}"])
        opts.extend(["-o", "StrictHostKeyChecking=yes"])
    elif _ssh_strict():
        opts.extend(["-o", "StrictHostKeyChecking=yes"])
    else:
        opts.extend(["-o", "StrictHostKeyChecking=accept-new"])
    opts.extend(_ssh_mux_opts())
    return opts


def _role_for_host(host: str) -> str | None:
    """Infer the role name for ``host`` from the hosts config, if any."""
    roles = _role_hosts()
    for role, role_host in roles.items():
        if role_host == host:
            return role
    return None


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
AITBC_CLI = _aitbc_cli_path()

# Logical service names accepted by ``aitbc http call``. The base URLs and
# ports live in the CLI, not the MCP server, so no local network topology is
# hardcoded here.
HTTP_SERVICE_NAMES = {
    "blockchain-rpc",
    "coordinator-api",
    "api-gateway",
    "market",
    "exchange",
    "wallet",
    "agent-coordinator",
    "gpu",
    "blockchain-explorer",
    "pool-hub",
    "blockchain-event-bridge",
    "monitoring",
    "trading",
    "governance",
    "ipfs",
    "whisper",
    "ffmpeg",
    "ollama",
}


def _normalize_http_service_name(service: str) -> str:
    """Normalize a service name, accepting both logical and systemd-style names.

    Allows callers to use either the logical name (e.g. 'blockchain-rpc') or
    the systemd unit name (e.g. 'aitbc-blockchain-rpc'), and also underscores
    instead of dashes.
    """
    service = service.lower().strip().replace("_", "-")
    if service.startswith("aitbc-"):
        service = service[6:]
    return service


# Canonical wallet directory on live AITBC nodes.  Used as AITBC_WALLET_DIR for
# any CLI command that signs transactions or needs a wallet file.
DEFAULT_WALLET_DIR = "/var/lib/aitbc/wallets"


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


# Root for agent-created scratch space on the live nodes. Callers may point
# env/cwd only underneath it so a remote command cannot be redirected at
# /etc, /var/lib/aitbc, or another user's home.
SCRATCH_ROOT = "/var/tmp"  # nosec B108 — deliberate: env/cwd are restricted to underneath this root so remote commands cannot be redirected at /etc, /var/lib/aitbc or user homes.

# Environment names accepted through the generic CLI tools' ``env`` parameter:
# ``HOME`` plus non-secret ``AITBC_*`` names. The use case is scratch-wallet
# and scratch-data plays; credential-shaped names stay refused.
CLI_ENV_ALLOWED_EXACT = frozenset({"HOME"})
CLI_ENV_ALLOWED_PREFIX = "AITBC_"
CLI_ENV_FORBIDDEN_TOKENS = (
    "KEY",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "JWT",
    "MNEMONIC",
    "SEED",
    "PRIVATE",
    "CREDENTIAL",
)


def _is_scratch_path(value: str) -> bool:
    """True when ``value`` is ``/var/tmp`` itself or a path beneath it."""
    norm = os.path.normpath(value)
    return norm == SCRATCH_ROOT or norm.startswith(SCRATCH_ROOT + "/")


def _is_allowed_env_name(name: str) -> bool:
    if name in CLI_ENV_ALLOWED_EXACT:
        return True
    return name.startswith(CLI_ENV_ALLOWED_PREFIX) and not any(token in name for token in CLI_ENV_FORBIDDEN_TOKENS)


def _validate_cli_env(env: dict[str, str] | None) -> str | None:
    """Validate the generic tools' ``env`` parameter. Returns an error message or None."""
    if not env:
        return None
    for name, value in env.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            return f"invalid environment variable name: {name!r}"
        if not _is_allowed_env_name(name):
            return f"environment variable not allowed: {name!r} (allow-list: HOME, non-secret AITBC_* names)"
        if not isinstance(value, str) or not _is_scratch_path(value):
            return f"environment value must be a path under {SCRATCH_ROOT}/: {name}={value!r}"
    return None


def _validate_cli_env_cwd(env: dict[str, str] | None, cwd: str | None) -> str | None:
    """Validate ``env`` and ``cwd`` together for the generic CLI tools."""
    error = _validate_cli_env(env)
    if error:
        return error
    if cwd is not None and not _is_scratch_path(cwd):
        return f"cwd must be a path under {SCRATCH_ROOT}/: {cwd!r}"
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Safe shape for an explicit host override: an ssh-config alias, hostname, IP
# literal, or optional ``user@`` prefix. Leading ``-`` and whitespace/``=`` are
# excluded so the value can never become an ssh option token in argv.
_HOST_PATTERN = re.compile(r"^(?:[A-Za-z0-9_.]+@)?[A-Za-z0-9_][A-Za-z0-9_.:\-]*$")


def _host_for_role(role: str | None, host: str | None = None) -> str:
    """Resolve the SSH host for a node role or an explicit host.

    ``role`` and ``host`` are mutually exclusive: passing both is refused so a
    caller can never silently land on a different node than the role intends.
    An unknown role is refused instead of falling through to be used as the
    ssh target itself. Explicit hosts are validated against ``_HOST_PATTERN``
    so a value cannot be parsed as an ssh option.
    """
    if host and role:
        raise ToolError("pass either role or host, not both")
    if host:
        if not _HOST_PATTERN.fullmatch(host):
            raise ToolError(f"invalid host override: {host!r}")
        return host
    if role:
        resolved = _role_hosts().get(role)
        if not resolved:
            raise ToolError(f"unknown role: {role}")
        return resolved
    return _default_host()


def _ssh_target(host: str) -> str:
    """Prefix host with SSH user if configured and not already present."""
    user = _ssh_user()
    if "@" not in host and user:
        return f"{user}@{host}"
    return host


def _is_local_host(host: str) -> bool:
    """Return True when the target host is the machine the server runs on."""
    if LOCAL_MODE:
        return True
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return socket.gethostname() == host
    except OSError:
        return False


def _execution_context(host: str) -> dict[str, str]:
    """Describe where a command for ``host`` runs: local shell or SSH.

    Included in tool results so the operator can see the resolved SSH target
    (including the user) or ``local``, plus the execution mode, before a
    confirmed call runs.
    """
    base = {"host": host, "resolved_host": host, "role_used": _role_for_host(host)}
    if _is_local_host(host):
        return {**base, "target": "local", "mode": "local"}
    return {**base, "target": _ssh_target(host), "mode": "ssh"}


def _decode_partial(value: Any) -> str:
    """Decode captured subprocess output to text.

    ``TimeoutExpired.stdout``/``.stderr`` stay ``bytes`` even with
    ``text=True`` (the exception is raised before decoding); stringifying
    them via ``default=str`` would emit ``b'\\xe2…'`` garbage (SM-09).
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


# Lines of each stream scanned for error patterns when stamping ``ok`` — deep
# enough to cover banner/wrapper lines, shallow enough that log-content reads
# mentioning errors well into the body do not flip the flag.
_RESULT_SCAN_LINES = 15

# First-line failure markers for the SP-13 class: CLI commands that exit 0
# while reporting an error in the body.  Deliberately narrow — a false
# ``ok:false`` on a successful read is worse than a missed flag, so every
# pattern is an explicit failure phrase:
#   - ``(?:^|(?<!\d)\s)failed\b(?!\s*[:,]?\s*\d)`` needs whitespace/line-start
#     before ``failed`` (JSON keys like ``"failed": 0`` never match) and
#     refuses the statistic forms ``failed: 0`` / ``0 failed, 5 passed`` /
#     ``0 failed`` — a *count* of failures is data, "… failed: <reason>" is a
#     report;
#   - the credential pattern pins ``found`` so the clean auth-status line
#     "No stored credentials for environment …" does not match;
#   - ``No <n> found`` forms are skipped entirely ("No agents found" is a
#     legitimate empty-list result).
_ERROR_LINE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^Error\b",
        r"^Network error\b",
        r"(?:^|(?<!\d)\s)failed\b(?!\s*[:,]?\s*\d)",
        r"\bnot found\b",
        r"\bunavailable\b|\bunreachable\b|not available",
        r"Connection refused|\[Errno \d+\]",
        r"^No stored credential found",
        r"^Traceback \(most recent call last\)",
        "✗",
        r'"error"\s*:\s*"[^"]',
        r"^Usage:",
        r"No such command|Got unexpected extra",
    )
)


def _error_hint(result: dict[str, Any]) -> str | None:
    """First error-pattern line in the head of stdout/stderr, trimmed.

    Returns ``None`` when no pattern matches; used to stamp ``ok:false`` on
    exit-0-with-error results (SP-13 / SM-07).
    """
    for stream in ("stdout", "stderr"):
        for line in str(result.get(stream) or "").splitlines()[:_RESULT_SCAN_LINES]:
            stripped = line.strip()
            if stripped and any(p.search(stripped) for p in _ERROR_LINE_PATTERNS):
                return stripped[:200]
    return None


def _result_status(result: dict[str, Any]) -> dict[str, Any]:
    """Stamp the failure signal onto a command-result envelope.

    Every envelope carrying ``returncode`` gets ``ok`` and ``exit_code``:
    ``ok`` is ``returncode == 0`` *and* no error pattern in the first lines of
    stdout/stderr (exit-0-with-error, SP-13/SM-07).  When the pattern — not
    the return code — made ``ok`` false, ``error_hint`` names the line.
    """
    if "returncode" not in result:
        return result
    rc = result["returncode"]
    result["exit_code"] = rc
    hint = _error_hint(result)
    if rc != 0:
        result["ok"] = False
    elif hint is not None:
        result["ok"] = False
        result["error_hint"] = hint
    else:
        result["ok"] = True
    return result


def _timeout_result(context: dict[str, str], command: str, timeout: int, e: subprocess.TimeoutExpired) -> dict[str, Any]:
    stderr_parts = [f"timeout after {timeout}s"]
    partial_err = _decode_partial(e.stderr)
    if partial_err.strip():
        stderr_parts.append(partial_err.strip())
    return {
        **context,
        "command": command,
        "returncode": -1,
        "timed_out": True,
        "stdout": _decode_partial(e.stdout),
        "stderr": "\n".join(stderr_parts),
    }


_ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _split_posix_prefix(command: str) -> tuple[dict[str, str], str | None, list[str]]:
    """Peel POSIX prefixes off a command string for a direct ``execvp``.

    Command strings may carry a ``cd <dir> &&`` working-directory clause
    followed by ``NAME=value`` environment assignments. The remote login
    shell interprets those prefixes; a local ``shlex.split`` + ``execvp``
    would treat ``cd`` or ``NAME=value`` as the program name, so the local
    branch of :func:`_run_remote` applies them as real child settings
    instead.

    Returns ``(env, cwd, argv)``.
    """
    argv = shlex.split(command)
    cwd: str | None = None
    env: dict[str, str] = {}
    if len(argv) >= 3 and argv[0] == "cd" and argv[2] == "&&":
        cwd = argv[1]
        argv = argv[3:]
    while argv and _ENV_ASSIGNMENT_RE.match(argv[0]):
        name, _, value = argv.pop(0).partition("=")
        env[name] = value
    return env, cwd, argv


def _run_remote(host: str, command: str, timeout: int = 60) -> dict[str, Any]:
    """Run a single command on an AITBC host, using a local shell when possible."""
    context = _execution_context(host)
    if context["mode"] == "local":
        env, cwd, argv = _split_posix_prefix(command)
        child_env = None
        if env:
            child_env = {**os.environ, **env}
        try:
            res = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                env=child_env,
                cwd=cwd,
                # Never let a CLI child read this process's stdin: the MCP
                # server speaks the stdio protocol on it.
                stdin=subprocess.DEVNULL,
            )
            return _result_status(
                {
                    **context,
                    "command": command,
                    "returncode": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                }
            )
        except subprocess.TimeoutExpired as e:
            return _result_status(_timeout_result(context, command, timeout, e))
        except FileNotFoundError as e:
            return _result_status(
                {
                    **context,
                    "command": command,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"command not found: {e.filename}",
                }
            )

    cmd = ["ssh"] + _ssh_opts(host) + [context["target"], "--", command]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return _result_status(
            {
                **context,
                "command": command,
                "returncode": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
        )
    except subprocess.TimeoutExpired as e:
        return _result_status(_timeout_result(context, command, timeout, e))
    except FileNotFoundError:
        return _result_status(
            {
                **context,
                "command": command,
                "returncode": -1,
                "stdout": "",
                "stderr": "ssh not found on MCP host",
            }
        )


def _json(result: Any) -> str:
    """Serialize a result to a pretty-printed JSON string.

    Envelope convention: a top-level ``"error"`` key means the call failed, so
    ``ok`` is stamped ``False`` when the caller did not set it; a ``dry_run``
    envelope is a well-formed preview and gets ``ok: true``.  Command-result
    envelopes carry ``ok``/``exit_code``/``timed_out`` from
    :func:`_result_status`.

    Every tool module returns through here, so this is where echoed command
    lines are masked (MCP-ECHO-1): :func:`aitbc_mcp_mask.mask_envelope`
    works on a copy and never sees the argv that was executed.
    """
    if isinstance(result, dict) and "ok" not in result:
        if "error" in result:
            result["ok"] = False
        elif result.get("dry_run"):
            result["ok"] = True
    return json.dumps(mask_envelope(result), indent=2, default=str)


def _safe_command(command: str) -> tuple[bool, list[str]]:
    """Parse and validate a command string.  Returns (ok, tokens)."""
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return False, [f"invalid shell quoting: {e}"]
    for token in tokens:
        if re.search(r"[;&|<>$`\\!\n\r]", token):
            return False, [f"disallowed shell metacharacter in token: {token}"]
    return True, tokens


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
    for key, value in (group_options or {}).items():
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

    for token in _subcommand_tokens(subcommand):
        tokens.append(shlex.quote(str(token)))

    for arg in args or []:
        tokens.append(shlex.quote(str(arg)))

    # Subcommand-level options appear after positional arguments.
    for key, value in (subcommand_options or options or {}).items():
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


def _run_aitbc_cli(
    host: str,
    group: str,
    subcommand: str | list[str] | None,
    args: list[str] | None,
    options: dict[str, Any] | None,
    output_format: str = "json",
    timeout: int = 120,
    *,
    group_options: dict[str, Any] | None = None,
    subcommand_options: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run an aitbc CLI subcommand on a remote host and optionally parse JSON."""
    command = _build_aitbc_cli_command(
        group,
        subcommand,
        args,
        options,
        output_format,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env=env,
        cwd=cwd,
    )
    result = _run_remote(host, command, timeout)
    if output_format == "json" and result.get("returncode") == 0:
        try:
            result["json"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass
    return result


def _aitbc_cli_read_tool(
    role: str | None,
    host: str | None,
    group: str,
    subcommand: str | list[str] | None = None,
    args: list[str] | None = None,
    options: dict[str, Any] | None = None,
    timeout: int = 120,
    *,
    group_options: dict[str, Any] | None = None,
    subcommand_options: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str:
    """Helper for read-only aitbc CLI tools."""
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )
    return _json(
        _run_aitbc_cli(
            target,
            group,
            subcommand,
            args,
            options,
            "json",
            timeout,
            group_options=group_options,
            subcommand_options=subcommand_options,
            env=env,
            cwd=cwd,
        )
    )


def _run_http(
    host: str,
    service: str,
    path: str,
    method: str = "GET",
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
    auth: str = "none",
    auth_env: str = "/etc/aitbc/aitbc-coordinator-api.env",
    expect_status: list[int] | None = None,
) -> dict[str, Any]:
    """Call an AITBC HTTP endpoint on a remote node via the ``aitbc http`` CLI.

    The actual base URLs and service ports live in the CLI so the MCP server
    does not carry local network topology.
    """
    service = _normalize_http_service_name(service)
    if service not in HTTP_SERVICE_NAMES:
        return {
            "error": f"unknown HTTP service: {service}",
            "known_services": sorted(HTTP_SERVICE_NAMES),
        }

    options: dict[str, Any] = {"method": method.upper(), "timeout": str(timeout)}
    if params:
        options["params"] = json.dumps(params, default=str)
    if body:
        options["body"] = json.dumps(body, default=str)
    if auth in ("miner", "rpc", "trading"):
        options["auth"] = auth
    if expect_status:
        options["expect-status"] = [str(s) for s in expect_status]
    # auth_env is intentionally ignored: the CLI resolves the API key from its
    # own config / env file lookup, which already checks the default path.

    return _run_aitbc_cli(
        host,
        "http",
        "call",
        [service, path],
        options,
        output_format="json",
        timeout=timeout,
    )


def _http_dry_run_command(
    service: str,
    path: str,
    method: str,
    params: dict[str, str] | None,
    body: dict[str, Any] | None,
    auth: str,
    expect_status: list[int] | None = None,
) -> str:
    """Build the representative CLI command shown in dry-run responses."""
    options: dict[str, Any] = {"method": method.upper()}
    if params:
        options["params"] = json.dumps(params, default=str)
    if body:
        options["body"] = json.dumps(body, default=str)
    if auth in ("miner", "rpc", "trading"):
        options["auth"] = auth
    if expect_status:
        options["expect-status"] = [str(s) for s in expect_status]
    return _build_aitbc_cli_command(
        "http",
        "call",
        [service, path],
        options,
        output_format="json",
    )


def _http_read_tool(
    role: str | None,
    host: str | None,
    service: str,
    path: str,
    params: dict[str, str] | None = None,
    timeout: int = 30,
) -> str:
    """Helper for read-only HTTP tools."""
    target = _host_for_role(role, host)
    service = _normalize_http_service_name(service)
    if service not in HTTP_SERVICE_NAMES:
        return _json(
            {
                "error": f"unknown HTTP service: {service}",
                "known_services": sorted(HTTP_SERVICE_NAMES),
            }
        )
    return _json(_run_http(target, service, path, "GET", params, None, timeout))


def _build_dry_run(message: str, real_command: str, host: str | None = None) -> dict[str, Any]:
    """Build the dry-run response for ``real_command``.

    When ``host`` is given the response names where a confirmed call would
    run: the SSH target (including the user) or ``local``, plus the execution
    mode.
    """
    result: dict[str, Any] = {"dry_run": True}
    if host is not None:
        result.update(_execution_context(host))
    result["command"] = real_command
    result["note"] = message
    return result


def _require_confirm(
    dry_run: bool,
    confirm: bool,
    command: str,
    host: str | None = None,
) -> dict[str, Any] | None:
    """Return an error response if the user did not confirm a real run."""
    if dry_run:
        return _build_dry_run(
            "This is a dry run. Set dry_run=false and confirm=true to execute.",
            command,
            host=host,
        )
    if not confirm:
        result: dict[str, Any] = {
            "error": "Confirmation required",
            "command": command,
            "note": "This is a destructive action. Pass dry_run=false and confirm=true to execute.",
        }
        if host is not None:
            result.update(_execution_context(host))
        return result
    return None


# ---------------------------------------------------------------------------
# Additional typed CLI tools from the companion module
# ---------------------------------------------------------------------------

# When this file is executed as a script the module is named __main__.  The
# companion modules do ``from aitbc_mcp_server import mcp``; register the
# __main__ module under its real name so they import the same mcp instance and
# tools are registered on the server that is actually started.
if __name__ == "__main__":
    sys.modules["aitbc_mcp_server"] = sys.modules["__main__"]

from aitbc_mcp_node_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    list_nodes,
    node_status,
    get_service_health,
    get_chain_height,
    get_block,
    get_trigger_status,
    list_rebalance_triggers,
    list_cron_jobs,
)

from aitbc_mcp_control_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    start_node,
    stop_node,
    restart_node,
    run_cron_job,
    run_aitbc_command,
)

from aitbc_mcp_cli_pivot_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    run_aitbc_cli,
    read_aitbc_cli,
    list_aitbc_cli_group,
    get_aitbc_version,
    get_auth_status,
    list_wallets,
    get_wallet_balance,
    list_wallet_transactions,
    list_ai_jobs,
    get_ai_job_status,
    get_ai_job_results,
    list_market_offers,
    get_market_status,
    list_aitbc_node_config,
    get_node_info,
    list_accounts,
    get_account,
    get_bond_status,
    list_pending_transactions,
    get_transaction_status,
    search_transactions,
    get_service_logs,
    get_service_status,
    get_systemd_unit,
    get_systemd_show,
    get_remote_file,
    restart_service,
)

from aitbc_mcp_ops_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    check_aitbc_system_health,
    list_aitbc_ipfs_pins,
    get_aitbc_agent_status,
    get_aitbc_agent_inbox,
    get_aitbc_dashboard_customer,
    get_aitbc_dashboard_shop,
)

from aitbc_mcp_http_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    call_aitbc_http,
    get_blockchain_info,
    get_blockchain_head,
    list_blocks,
    get_block_info,
    get_account_info,
    get_transaction_info,
    get_mempool,
    get_network_info,
    get_blockchain_status,
)

from aitbc_mcp_mutating_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    submit_ai_job,
    pay_for_ai_job,
    manage_ai_job,
    get_zk_refund_sweep_candidates,
    run_zk_refund_sweep,
    send_aitbc_transaction,
    create_performance_bond,
    stake_aitbc,
    unstake_aitbc,
)

from aitbc_mcp_chain_tools import (  # noqa: F401  # re-exports moved tools as mcp_server.<name>
    query_blockchain_transactions,
    get_account_balance,
    reconcile_account_balance,
    get_account_state_snapshot,
    get_account_state_delta,
    get_genesis_allocations,
    get_sync_config,
    list_chains,
    get_consensus_status,
    list_validators,
    get_staking_info,
    get_bond,
    list_provider_bonds,
    get_bridge_transfer,
    list_pending_bridge_transfers,
    get_cross_chain_rates,
    get_cross_chain_pools,
    list_gpus,
    get_gpu_info,
    list_ai_jobs_onchain,
    get_ai_job_onchain,
    get_escrow_state,
    list_islands,
    get_island,
)

import aitbc_mcp_cli_tools  # noqa: F401  # registers more CLI tools
import aitbc_mcp_cli_tools_generated  # noqa: F401  # registers auto-generated CLI tools

# ---------------------------------------------------------------------------
# Additional typed RPC tools from the companion module
# ---------------------------------------------------------------------------

import aitbc_mcp_rpc_tools  # noqa: F401  # registers more RPC tools

# ---------------------------------------------------------------------------
# Additional typed ZK tools from the companion module
# ---------------------------------------------------------------------------

import aitbc_mcp_zk_tools  # noqa: F401  # registers ZK tools

# ---------------------------------------------------------------------------
# Additional typed liquidity-pool tools from the companion module
# ---------------------------------------------------------------------------

import aitbc_mcp_liquidity_tools  # noqa: F401  # registers liquidity tools


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
