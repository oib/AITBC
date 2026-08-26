#!/usr/bin/env python3
"""AITBC Model Context Protocol (MCP) server.

Exposes tools for operating AITBC nodes over SSH on the live AITBC hosts
(aitbc3 and hub.aitbc).  Capabilities are intentionally safe by default:

* Read-only inspection tools use ``ToolAnnotations(read_only_hint=True)``.
* Destructive tools default to ``dry_run=True`` and additionally require
  ``confirm=True`` before they actually execute a command on a remote host.

Environment variables
---------------------
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
import subprocess
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

mcp = MCPServer("aitbc", log_level=os.getenv("AITBC_MCP_LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROLE_HOSTS = {
    "hub": "hub.aitbc",
    "customer": "hub.aitbc",
    "shop": "aitbc3",
    "follower": "aitbc3",
}

SSH_USER = os.getenv("AITBC_MCP_SSH_USER", "")
DEFAULT_HOST = os.getenv("AITBC_MCP_DEFAULT_HOST", "hub.aitbc")

# Conservative SSH options: no interactive prompts, time out quickly, accept a
# new host key on first connection (the host can later be pinned via Devin).
SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=accept-new",
]

AITBC_CLI = "/opt/aitbc/venv/bin/aitbc"

# Scripts/cron jobs the server is allowed to execute.
ALLOWED_SCRIPT_PREFIXES = (
    "/opt/aitbc/scripts/",
    "/opt/aitbc/monitoring/",
    "/opt/aitbc/cluster/",
)

# AITBC health endpoint catalogue, copied from scripts/monitoring/health_check.sh.
# These are used for the optional per-service health probe.
ALL_SERVICE_ENDPOINTS = {
    "aitbc-blockchain-rpc": "http://localhost:8202/health",
    "aitbc-wallet": "http://localhost:8108/health",
    "aitbc-trading": "http://localhost:8104/health",
    "aitbc-governance": "http://localhost:8105/health",
    "aitbc-coordinator-api": "http://localhost:8203/health",
    "aitbc-api-gateway": "http://localhost:8201/health",
    "aitbc-exchange": "http://localhost:8106/health",
    "aitbc-marketplace": "http://localhost:8102/health",
    "aitbc-agent-coordinator": "http://localhost:8107/health",
    "aitbc-blockchain-explorer": "http://localhost:8100/health",
    "aitbc-blockchain-event-bridge": "http://localhost:8205/health",
    "aitbc-gpu": "http://localhost:8101/health",
    "aitbc-edge": "http://localhost:8111/health",
    "aitbc-pool-hub": "http://localhost:8210/health",
    "aitbc-island-ipfs": "http://localhost:5002/api/v0/version",
    "aitbc-whisper": "http://localhost:8110/health",
    "aitbc-ffmpeg": "http://localhost:8230/health",
    "aitbc-monitoring": "http://localhost:8002/health",
    "ollama": "http://localhost:11434/api/tags",
}

# Base URLs for the AITBC HTTP APIs (used by call_aitbc_http).  These map a
# logical service name to the port the service listens on locally on a node.
ALL_SERVICE_BASES = {
    "blockchain-rpc": "http://localhost:8202/rpc",
    "coordinator-api": "http://localhost:8203",
    "api-gateway": "http://localhost:8201",
    "marketplace": "http://localhost:8102",
    "exchange": "http://localhost:8106",
    "wallet": "http://localhost:8108",
    "agent-coordinator": "http://localhost:8107",
    "gpu": "http://localhost:8101",
    "blockchain-explorer": "http://localhost:8100",
    "pool-hub": "http://localhost:8210",
    "blockchain-event-bridge": "http://localhost:8205",
    "monitoring": "http://localhost:8002",
    "trading": "http://localhost:8104",
    "governance": "http://localhost:8105",
    "ipfs": "http://localhost:5002",
    "whisper": "http://localhost:8110",
    "ffmpeg": "http://localhost:8230",
    "ollama": "http://localhost:11434",
}

# Set of service names available to call_aitbc_http.
ALL_HTTP_SERVICES = set(ALL_SERVICE_BASES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _host_for_role(role: str | None, host: str | None = None) -> str:
    """Resolve the SSH host for a node role or an explicit host."""
    if host:
        return host
    if role:
        return ROLE_HOSTS.get(role, role)
    return DEFAULT_HOST


def _ssh_target(host: str) -> str:
    """Prefix host with SSH user if configured and not already present."""
    if "@" not in host and SSH_USER:
        return f"{SSH_USER}@{host}"
    return host


def _run_remote(host: str, command: str, timeout: int = 60) -> dict[str, Any]:
    """Run a single command on a remote AITBC host over SSH."""
    target = _ssh_target(host)
    cmd = ["ssh"] + SSH_OPTS + [target, "--", command]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "host": host,
            "command": command,
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "host": host,
            "command": command,
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": f"timeout after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "host": host,
            "command": command,
            "returncode": -1,
            "stdout": "",
            "stderr": "ssh not found on MCP host",
        }


def _json(result: Any) -> str:
    """Serialize a result to a pretty-printed JSON string."""
    return json.dumps(result, indent=2, default=str)


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


def _is_allowed_script(path: str) -> bool:
    """Check that a script path is within the allowed AITBC tree."""
    return any(path.startswith(prefix) for prefix in ALLOWED_SCRIPT_PREFIXES)


# ---------------------------------------------------------------------------
# AITBC CLI pivot helpers
# ---------------------------------------------------------------------------

# Live/validated top-level aitbc CLI groups (from ``aitbc --help`` without
# ``--show-deprecated``).  The generic ``run_aitbc_cli`` tool is restricted to
# these groups; typed wrappers are provided for the most common subcommands.
ALL_AITBC_GROUPS = {
    "account",
    "agent",
    "ai",
    "auth",
    "bond",
    "bridge",
    "config",
    "dashboard",
    "exchange",
    "exchange-island",
    "explorer",
    "gpu",
    "governance",
    "ipfs",
    "list",
    "market",
    "marketplace",
    "node",
    "restart",
    "start",
    "stop",
    "system",
    "transactions",
    "version",
    "wallet",
}

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
}


def _safe_option_key(key: str) -> bool:
    """Validate a CLI option name: only letters, digits, dashes and underscores."""
    return bool(re.match(r"^[A-Za-z0-9_-]+$", key))


def _build_aitbc_cli_command(
    group: str,
    subcommand: str | None = None,
    args: list[str] | None = None,
    options: dict[str, str | None] | None = None,
    output_format: str = "json",
) -> str:
    """Build a quoted aitbc CLI command string.

    Global options like ``--output`` are placed before the group. Group-specific
    options are placed after the group but before the subcommand to match how
    Click parses them, e.g.::

        aitbc --output json wallet --wallet-name genesis balance
    """
    tokens: list[str] = [AITBC_CLI]
    if output_format in {"json", "yaml", "csv"}:
        tokens.append(f"--output={output_format}")
    tokens.append(shlex.quote(group))
    if subcommand:
        tokens.append(shlex.quote(subcommand))
    for arg in args or []:
        tokens.append(shlex.quote(str(arg)))
    for key, value in (options or {}).items():
        if not _safe_option_key(key):
            raise ValueError(f"invalid option key: {key}")
        if value is None or value == "":
            tokens.append(f"--{key}")
        else:
            tokens.append(f"--{key}={shlex.quote(str(value))}")
    return " ".join(tokens)


def _is_aitbc_subcommand_destructive(subcommand: str | None) -> bool:
    """Return True when a subcommand is known to mutate state."""
    return subcommand in DESTRUCTIVE_AITBC_SUBCOMMANDS if subcommand else False


def _run_aitbc_cli(
    host: str,
    group: str,
    subcommand: str | None,
    args: list[str] | None,
    options: dict[str, str | None] | None,
    output_format: str = "json",
    timeout: int = 120,
) -> dict[str, Any]:
    """Run an aitbc CLI subcommand on a remote host and optionally parse JSON."""
    command = _build_aitbc_cli_command(group, subcommand, args, options, output_format)
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
    subcommand: str | None = None,
    args: list[str] | None = None,
    options: dict[str, str | None] | None = None,
    timeout: int = 120,
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
    return _json(_run_aitbc_cli(target, group, subcommand, args, options, "json", timeout))


def _build_http_url(base: str, path: str, params: dict[str, str] | None) -> str:
    """Build a local HTTP URL with query parameters."""
    url = base.rstrip("/") + "/" + path.lstrip("/")
    if params:
        url += "?" + urlencode(params)
    return url


def _run_http(
    host: str,
    service: str,
    path: str,
    method: str = "GET",
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Call an AITBC HTTP endpoint on a remote node via curl."""
    base = ALL_SERVICE_BASES.get(service)
    if not base:
        return {
            "error": f"unknown service: {service}",
            "known_services": sorted(ALL_SERVICE_BASES),
        }

    url = _build_http_url(base, path, params)
    method = method.upper()
    if method == "GET":
        command = f"curl -sS {shlex.quote(url)}"
    else:
        headers = "-H 'Content-Type: application/json'"
        if body:
            payload = shlex.quote(json.dumps(body))
            command = f"curl -sS -X {method} {headers} -d {payload} {shlex.quote(url)}"
        else:
            command = f"curl -sS -X {method} {shlex.quote(url)}"

    result = _run_remote(host, command, timeout)
    if result.get("returncode") == 0:
        try:
            result["json"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass
    return result


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
    if service not in ALL_HTTP_SERVICES:
        return _json(
            {
                "error": f"unknown HTTP service: {service}",
                "known_services": sorted(ALL_HTTP_SERVICES),
            }
        )
    return _json(_run_http(target, service, path, "GET", params, None, timeout))


def _build_dry_run(message: str, real_command: str) -> dict[str, Any]:
    return {
        "dry_run": True,
        "command": real_command,
        "note": message,
    }


def _require_confirm(
    dry_run: bool,
    confirm: bool,
    command: str,
) -> dict[str, Any] | None:
    """Return an error response if the user did not confirm a real run."""
    if dry_run:
        return _build_dry_run(
            "This is a dry run. Set dry_run=false and confirm=true to execute.",
            command,
        )
    if not confirm:
        return {
            "error": "Confirmation required",
            "command": command,
            "note": "This is a destructive action. Pass dry_run=false and confirm=true to execute.",
        }
    return None


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_nodes() -> str:
    """List the AITBC nodes and roles this MCP server can reach."""
    return _json(
        {
            "nodes": [
                {"role": "hub", "host": ROLE_HOSTS["hub"], "site": "hub/customer node"},
                {"role": "customer", "host": ROLE_HOSTS["customer"], "site": "hub/customer node"},
                {"role": "shop", "host": ROLE_HOSTS["shop"], "site": "shop/follower node"},
                {"role": "follower", "host": ROLE_HOSTS["follower"], "site": "shop/follower node"},
            ],
            "environment": {
                "default_host": DEFAULT_HOST,
                "ssh_user": SSH_USER or "(current user)",
            },
            "note": ("Connections use passwordless SSH. Set AITBC_MCP_SSH_USER and AITBC_MCP_DEFAULT_HOST in the MCP env."),
        }
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def node_status(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query (uses default host if omitted)."),
    ] = None,
    service: Annotated[
        str | None,
        Field(description="Check a single systemd unit instead of the whole role."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get systemd status for AITBC services on a node."""
    target = _host_for_role(role, host)
    if service:
        command = (
            f"bash -c 'state=$(systemctl is-active {service} 2>/dev/null || true); "
            f'[ -n "$state" ] || state=unknown; '
            f"props=$(systemctl show {service} --property=ActiveState,SubState,LoadState,MainPID 2>/dev/null); "
            f'printf "%s\\t%s\\n%s\\n" "{service}" "$state" "$props"\''
        )
    else:
        command = (
            "bash -c 'source /opt/aitbc/scripts/monitoring/health_check.sh >/dev/null 2>&1; "
            "for svc in ${ROLE_SERVICES[@]}; do "
            "state=$(systemctl is-active $svc 2>/dev/null || true); "
            '[ -n "$state" ] || state=unknown; '
            'printf "%s\\t%s\\n" "$svc" "$state"; '
            "done'"
        )
    return _json(_run_remote(target, command, timeout=30))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_service_health(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    service: Annotated[
        str | None,
        Field(description="Probe a single service by systemd unit name."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Query the HTTP /health endpoint for AITBC services."""
    target = _host_for_role(role, host)
    if service:
        url = ALL_SERVICE_ENDPOINTS.get(service)
        if not url:
            return _json({"error": f"no known health endpoint for {service}"})
        return _json(_run_remote(target, f"curl -sf -w '%{{http_code}}' {url} -o /dev/null", timeout=20))

    # Probe all services for the role that have HTTP endpoints.
    script = (
        "bash -c 'source /opt/aitbc/scripts/monitoring/health_check.sh >/dev/null 2>&1; "
        "for svc in ${ROLE_SERVICES[@]}; do "
        "  url=${ALL_SERVICE_ENDPOINTS[$svc]:-}; "
        '  [ -z "$url" ] && continue; '
        '  code=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true); [ -z "$code" ] && code=000; '
        '  printf "%s\\t%s\\n" "$svc" "$code"; '
        "done'"
    )
    return _json(_run_remote(target, script, timeout=30))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_chain_height(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current blockchain height from the node's RPC."""
    target = _host_for_role(role, host)
    return _json(_run_remote(target, "curl -sS http://localhost:8202/rpc/height", timeout=20))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_block(
    height: Annotated[
        int,
        Field(description="Block height to retrieve.", ge=0),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a block by height from the node's RPC."""
    target = _host_for_role(role, host)
    return _json(_run_remote(target, f"curl -sS http://localhost:8202/rpc/blocks/{height}", timeout=20))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_trigger_status(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get blockchain event bridge trigger and action metrics."""
    target = _host_for_role(role, host)
    command = (
        'bash -c \'echo "=== service status ==="; '
        "systemctl is-active aitbc-blockchain-event-bridge 2>/dev/null || true; "
        'echo "=== bridge metrics ==="; '
        'curl -sfL http://localhost:8205/metrics/ 2>/dev/null | grep -E "^bridge_(actions|events)_" | head -50\''
    )
    return _json(_run_remote(target, command, timeout=20))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_rebalance_triggers() -> str:
    """List the agent/economic rebalancing trigger types and action types."""
    return _json(
        {
            "rebalancing_triggers": ["threshold", "schedule", "opportunity"],
            "rebalance_action_types": ["buy", "sell", "transfer", "stake", "reinvest", "hold"],
            "constraint_types": ["max_exposure", "min_liquidity", "diversification", "min_reinvest_amount"],
            "note": (
                "For a concrete rebalance plan, fetch an agent's holdings and "
                "ReinvestmentPolicy from the coordinator API or wallet and use the "
                "Rebalancer class in aitbc.agent_economics.rebalance."
            ),
        }
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_cron_jobs(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List cron jobs for the AITBC user and /etc/cron.d entries."""
    target = _host_for_role(role, host)
    command = (
        'bash -c \'echo "=== user crontab ==="; '
        '(crontab -l 2>/dev/null) || echo "no user crontab"; '
        'echo "=== /etc/cron.d ==="; '
        "ls -1 /etc/cron.d/aitbc* 2>/dev/null || true; "
        "for f in /etc/cron.d/aitbc*; do "
        '  [ -f "$f" ] || continue; '
        '  echo "--- $f ---"; '
        '  cat "$f"; '
        "done'"
    )
    return _json(_run_remote(target, command, timeout=20))


# ---------------------------------------------------------------------------
# Destructive tools (dry-run by default)
# ---------------------------------------------------------------------------


def _control_node(
    action: str,
    role: Literal["hub", "customer", "shop", "follower"],
    dry_run: bool,
    confirm: bool,
    host: str | None = None,
) -> str:
    """Start, stop, or restart all role services on a node."""
    target = _host_for_role(role, host)
    real_command = f"sudo -n {AITBC_CLI} {action} --role {role}"
    guard = _require_confirm(dry_run, confirm, real_command)
    if guard is not None:
        return _json(guard)
    return _json(_run_remote(target, real_command, timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def start_node(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"],
        Field(description="Node role to start."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Start all AITBC services for the given node role."""
    return _control_node("start", role, dry_run, confirm, host)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def stop_node(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"],
        Field(description="Node role to stop."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Stop all AITBC services for the given node role."""
    return _control_node("stop", role, dry_run, confirm, host)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def restart_node(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"],
        Field(description="Node role to restart."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Restart all AITBC services for the given node role."""
    return _control_node("restart", role, dry_run, confirm, host)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_cron_job(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"],
        Field(description="Node role where the job runs."),
    ],
    script_path: Annotated[
        str,
        Field(description="Absolute path to the script under /opt/aitbc/ to execute."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Manually run an AITBC cron/script job on the selected node."""
    target = _host_for_role(role, host)
    if not _is_allowed_script(script_path):
        return _json(
            {
                "error": "script path not allowed",
                "path": script_path,
                "allowed_prefixes": ALLOWED_SCRIPT_PREFIXES,
            }
        )

    real_command = f"bash {shlex.quote(script_path)}"
    guard = _require_confirm(dry_run, confirm, real_command)
    if guard is not None:
        return _json(guard)

    return _json(_run_remote(target, real_command, timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_aitbc_command(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"],
        Field(description="Node role where the command runs."),
    ],
    command: Annotated[
        str,
        Field(description="The `aitbc` subcommand and arguments, e.g. 'chain height' or 'wallet list'."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run an `aitbc` CLI command on the selected node.

    Examples of ``command``:
    - ``chain height``
    - ``wallet list``
    - ``market list-offers``
    - ``ai list-jobs``
    """
    ok, tokens = _safe_command(command)
    if not ok:
        return _json({"error": "invalid command", "details": tokens})

    target = _host_for_role(role, host)
    quoted = " ".join(shlex.quote(t) for t in tokens)
    real_command = f"{AITBC_CLI} {quoted}"
    guard = _require_confirm(dry_run, confirm, real_command)
    if guard is not None:
        return _json(guard)

    return _json(_run_remote(target, real_command, timeout=120))


# ---------------------------------------------------------------------------
# AITBC CLI pivot tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_aitbc_cli(
    group: Annotated[
        str,
        Field(description="Live aitbc CLI group (e.g. 'wallet', 'market', 'ai', 'node')."),
    ],
    subcommand: Annotated[
        str,
        Field(description="Subcommand to run (e.g. 'list', 'status', 'submit')."),
    ],
    args: Annotated[
        list[str] | None,
        Field(description="Positional arguments for the subcommand."),
    ] = None,
    options: Annotated[
        dict[str, str | None] | None,
        Field(description="Options as --key=value. Use null for boolean flags."),
    ] = None,
    output_format: Annotated[
        Literal["json", "yaml", "csv", "table"],
        Field(description="Output format; JSON is preferred for machine parsing."),
    ] = "json",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the action."),
    ] = False,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=600),
    ] = 120,
) -> str:
    """Run an aitbc CLI command with structured group, subcommand, args and options.

    This is the generic pivot for any live aitbc CLI operation not covered by a
    dedicated wrapper. Destructive subcommands require ``dry_run=false`` and
    ``confirm=true``. Read-only subcommands require ``dry_run=false`` to run.

    Examples:
      - group="wallet", subcommand="list"
      - group="wallet", subcommand="balance", options={"wallet-name": "genesis"}
      - group="ai", subcommand="status", args=["<job-id>"]
      - group="market", subcommand="status", args=["<order-id>"]
      - group="node", subcommand="info", args=["<node-id>"]
    """
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )

    command = _build_aitbc_cli_command(group, subcommand, args, options, output_format)
    destructive = _is_aitbc_subcommand_destructive(subcommand)

    if dry_run:
        return _json(_build_dry_run("Set dry_run=false to execute.", command))

    if destructive and not confirm:
        return _json(
            {
                "error": "Confirmation required",
                "command": command,
                "note": ("This aitbc subcommand may mutate state. Pass dry_run=false and confirm=true to execute."),
            }
        )

    return _json(_run_aitbc_cli(target, group, subcommand, args, options, output_format, timeout))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_cli_group(
    group: Annotated[
        str,
        Field(description="Live aitbc CLI group to describe (e.g. 'wallet', 'market')."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the help output for a live aitbc CLI group."""
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )
    return _json(_run_remote(target, f"{AITBC_CLI} {shlex.quote(group)} --help"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_version(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the installed aitbc CLI version."""
    return _aitbc_cli_read_tool(role, host, "version", subcommand=None)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_auth_status(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show stored aitbc CLI authentication credentials (values are masked)."""
    return _aitbc_cli_read_tool(role, host, "auth", "status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_wallets(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List wallets known to the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "wallet", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_balance(
    wallet_name: Annotated[
        str,
        Field(description="Wallet name to query."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the balance of a named wallet."""
    return _aitbc_cli_read_tool(role, host, "wallet", "balance", args=[wallet_name])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_wallet_transactions(
    wallet_name: Annotated[
        str,
        Field(description="Wallet name to query."),
    ],
    limit: Annotated[
        int | None,
        Field(description="Maximum number of transactions to return.", ge=1),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List blockchain transactions for a wallet."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(role, host, "wallet", "transactions", args=[wallet_name], options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_ai_jobs(
    limit: Annotated[
        int | None,
        Field(description="Maximum number of jobs to return.", ge=1),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List AI jobs."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(role, host, "ai", "jobs", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_job_status(
    job_id: Annotated[
        str,
        Field(description="AI job ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of an AI job."""
    return _aitbc_cli_read_tool(role, host, "ai", "status", options={"job-id": job_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_job_results(
    job_id: Annotated[
        str,
        Field(description="AI job ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the results of a completed AI job."""
    return _aitbc_cli_read_tool(role, host, "ai", "results", options={"job-id": job_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_market_offers(
    limit: Annotated[
        int | None,
        Field(description="Maximum number of offers to return.", ge=1),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List GPU/software marketplace offers and bids."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(role, host, "market", "list", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_status(
    order_id: Annotated[
        str,
        Field(description="Marketplace order/escrow ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Check the status of a GPU order including on-chain escrow."""
    return _aitbc_cli_read_tool(role, host, "market", "status", args=[order_id])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_node_config(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List nodes configured in the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "node", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_node_info(
    node_id: Annotated[
        str,
        Field(description="Node ID to look up."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get detailed information about a configured aitbc node."""
    return _aitbc_cli_read_tool(role, host, "node", "info", args=[node_id])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_accounts(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List accounts tracked by the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "account", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account(
    address: Annotated[
        str,
        Field(description="Account address to look up."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get account information for a single address."""
    return _aitbc_cli_read_tool(role, host, "account", "get", options={"address": address})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bond_status(
    provider: Annotated[
        str,
        Field(description="Provider ID or address to look up."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show a provider's performance bond eligibility status."""
    return _aitbc_cli_read_tool(role, host, "bond", "status", args=[provider])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_pending_transactions(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get pending aitbc transactions."""
    return _aitbc_cli_read_tool(role, host, "transactions", "pending")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_transaction_status(
    tx_hash: Annotated[
        str,
        Field(description="Transaction hash."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of a transaction."""
    return _aitbc_cli_read_tool(role, host, "transactions", "status", args=[tx_hash])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def search_transactions(
    address: Annotated[
        str,
        Field(description="Address or node ID to search for."),
    ],
    limit: Annotated[
        int | None,
        Field(description="Maximum number of transactions to return.", ge=1),
    ] = None,
    use_explorer: Annotated[
        bool,
        Field(description="Use the Explorer API instead of RPC."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Search transactions by address or node ID."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    if use_explorer:
        options["use-explorer"] = ""
    return _aitbc_cli_read_tool(role, host, "transactions", "search", args=[address], options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_service_logs(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-blockchain-rpc'."),
    ],
    lines: Annotated[
        int,
        Field(description="Number of recent log lines to return.", ge=1, le=1000),
    ] = 50,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Tail systemd journal logs for an AITBC service."""
    target = _host_for_role(role, host)
    if re.search(r"[;&|<>$`\\!\n\r]", service):
        return _json({"error": "invalid service name", "service": service})
    command = f"journalctl -n {lines} -u {service} --no-pager"
    return _json(_run_remote(target, command, timeout=30))


# ---------------------------------------------------------------------------
# Phase 6 daily-use CLI wrappers
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def check_aitbc_system_health(
    service: Annotated[
        str | None,
        Field(description="Check a single systemd service by unit name (e.g. 'aitbc-coordinator-api')."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run `aitbc system check` to get a real multi-service readiness report."""
    options: dict[str, str] = {}
    if service is not None:
        options["service"] = service
    return _aitbc_cli_read_tool(role, host, "system", "check", options=options or None)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_ipfs_rentals(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List active IPFS hosting rentals."""
    return _aitbc_cli_read_tool(role, host, "ipfs", "rentals")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_ipfs_pins(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List locally pinned IPFS CIDs."""
    return _aitbc_cli_read_tool(role, host, "ipfs", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_agent_status(
    agent_id: Annotated[
        str | None,
        Field(description="Agent ID to look up."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of an agent (or the default local agent)."""
    args = [agent_id] if agent_id else None
    return _aitbc_cli_read_tool(role, host, "agent", "status", args=args)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_agent_inbox(
    agent_id: Annotated[
        str | None,
        Field(description="Agent ID to look up."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the inbox of an agent (or the default local agent)."""
    options: dict[str, str] = {}
    if agent_id is not None:
        options["agent-id"] = agent_id
    return _aitbc_cli_read_tool(role, host, "agent", "inbox", options=options or None)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_dashboard_customer(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the customer dashboard with live wallet balances and job status."""
    return _aitbc_cli_read_tool(role, host, "dashboard", "customer")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_dashboard_shop(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the shop dashboard with live balances and marketplace offers."""
    return _aitbc_cli_read_tool(role, host, "dashboard", "shop")


# ---------------------------------------------------------------------------
# HTTP / RPC pivot tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def call_aitbc_http(
    service: Annotated[
        str,
        Field(description="AITBC service name (e.g. 'blockchain-rpc', 'coordinator-api', 'marketplace')."),
    ],
    path: Annotated[
        str,
        Field(description="URL path after the service base, e.g. 'info', 'account/0x...', 'v1/jobs'."),
    ],
    method: Annotated[
        Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        Field(description="HTTP method."),
    ] = "GET",
    params: Annotated[
        dict[str, str] | None,
        Field(description="Query parameters as key/value pairs."),
    ] = None,
    body: Annotated[
        dict[str, Any] | None,
        Field(description="JSON body for POST/PUT/PATCH requests."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the curl command without executing it."),
    ] = False,
    confirm: Annotated[
        bool,
        Field(description="Confirm a mutating HTTP call."),
    ] = False,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=300),
    ] = 30,
) -> str:
    """Call an AITBC HTTP/RPC endpoint on a selected node.

    This is the generic HTTP pivot. GET calls can run directly; mutating methods
    (POST, PUT, PATCH, DELETE) require ``dry_run=false`` and ``confirm=true``.

    Examples:
      - service="blockchain-rpc", path="info"
      - service="blockchain-rpc", path="account/ait1..."
      - service="blockchain-rpc", path="blocks-range", params={"limit": "3"}
      - service="coordinator-api", path="v1/jobs", params={"limit": "10"}
    """
    target = _host_for_role(role, host)
    if service not in ALL_HTTP_SERVICES:
        return _json(
            {
                "error": f"unknown HTTP service: {service}",
                "known_services": sorted(ALL_HTTP_SERVICES),
            }
        )

    base = ALL_SERVICE_BASES[service]
    url = _build_http_url(base, path, params)
    command = f"curl -sS {shlex.quote(url)}"
    if method != "GET":
        headers = "-H 'Content-Type: application/json'"
        if body:
            payload = shlex.quote(json.dumps(body))
            command = f"curl -sS -X {method} {headers} -d {payload} {shlex.quote(url)}"
        else:
            command = f"curl -sS -X {method} {shlex.quote(url)}"

    if dry_run:
        return _json(_build_dry_run("Set dry_run=false to execute.", command))

    if method != "GET" and not confirm:
        return _json(
            {
                "error": "Confirmation required",
                "command": command,
                "note": "Mutating HTTP calls require dry_run=false and confirm=true.",
            }
        )

    return _json(_run_http(target, service, path, method, params, body, timeout))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_info(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get comprehensive blockchain information (height, tx count, accounts, genesis)."""
    return _http_read_tool(role, host, "blockchain-rpc", "info")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_head(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current chain head block."""
    return _http_read_tool(role, host, "blockchain-rpc", "head")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_blocks(
    start: Annotated[
        int | None,
        Field(description="Start height (inclusive).", ge=0),
    ] = None,
    end: Annotated[
        int | None,
        Field(description="End height (inclusive).", ge=0),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Return the most recent N blocks.", ge=1),
    ] = None,
    include_tx: Annotated[
        bool,
        Field(description="Include transactions in each block."),
    ] = True,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a range of blocks by height or the most recent N blocks."""
    params: dict[str, str] = {}
    if start is not None:
        params["start"] = str(start)
    if end is not None:
        params["end"] = str(end)
    if limit is not None:
        params["limit"] = str(limit)
    params["include_tx"] = "true" if include_tx else "false"
    return _http_read_tool(role, host, "blockchain-rpc", "blocks-range", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_block_info(
    height: Annotated[
        int,
        Field(description="Block height to retrieve.", ge=0),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a single block by height."""
    return _http_read_tool(role, host, "blockchain-rpc", f"blocks/{height}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account_info(
    address: Annotated[
        str,
        Field(description="Account address or bech32 address."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get account balance and nonce from the blockchain RPC."""
    return _http_read_tool(role, host, "blockchain-rpc", f"account/{address}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_transaction_info(
    tx_hash: Annotated[
        str,
        Field(description="Transaction hash with 0x prefix."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a transaction by hash from the blockchain RPC."""
    return _http_read_tool(role, host, "blockchain-rpc", f"transaction/{tx_hash}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_mempool(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get pending transactions in the mempool."""
    return _http_read_tool(role, host, "blockchain-rpc", "mempool")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_network_info(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get P2P, chain, and network configuration."""
    return _http_read_tool(role, host, "blockchain-rpc", "network-info")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_blockchain_status(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the blockchain node status."""
    return _http_read_tool(role, host, "blockchain-rpc", "status")


# ---------------------------------------------------------------------------
# Mutating aitbc CLI wrappers
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def submit_ai_job(
    prompt: Annotated[
        str,
        Field(description="Prompt or input for the AI job."),
    ],
    wallet: Annotated[
        str | None,
        Field(description="Wallet name to pay for the job."),
    ] = None,
    job_type: Annotated[
        str | None,
        Field(description="Job type, e.g. 'ollama', 'whisper', 'ffmpeg'."),
    ] = None,
    model: Annotated[
        str | None,
        Field(description="Ollama model to use (for ollama jobs)."),
    ] = None,
    payment: Annotated[
        str | None,
        Field(description="Payment amount, e.g. '0.1'"),
    ] = None,
    currency: Annotated[
        str,
        Field(description="Payment currency."),
    ] = "AITBC",
    offer_id: Annotated[
        str | None,
        Field(description="Marketplace offer ID this job is bought against."),
    ] = None,
    min_reputation: Annotated[
        float | None,
        Field(description="Minimum provider reputation (0-1).", ge=0, le=1),
    ] = None,
    buyer_address: Annotated[
        str | None,
        Field(description="Customer wallet address for escrow."),
    ] = None,
    provider_address: Annotated[
        str | None,
        Field(description="Provider wallet address for escrow."),
    ] = None,
    offer_quantity: Annotated[
        str | None,
        Field(description="How many of the offer's price units to buy."),
    ] = None,
    acceptance_window: Annotated[
        int | None,
        Field(description="Seconds after completion before payment auto-releases.", ge=0),
    ] = None,
    zk_proof_required: Annotated[
        bool,
        Field(description="Require a ZK receipt proof before escrow release."),
    ] = False,
    tee_attestation_required: Annotated[
        bool,
        Field(description="Require a TEE attestation before escrow release."),
    ] = False,
    tee_enclave_id: Annotated[
        str | None,
        Field(description="Required TEE enclave identity."),
    ] = None,
    confidential: Annotated[
        bool,
        Field(description="Mark this job as confidential (requires a TEE attestation)."),
    ] = False,
    enclave_measurement: Annotated[
        str | None,
        Field(description="Required enclave measurement for a confidential job."),
    ] = None,
    auto_reinvest_pct: Annotated[
        float | None,
        Field(description="Percentage of released payment to auto-stake as reinvestment.", ge=0, le=100),
    ] = None,
    bond_required: Annotated[
        bool,
        Field(description="Require the provider to have an active performance bond."),
    ] = False,
    min_bond_amount: Annotated[
        Decimal | None,
        Field(description="Minimum bond amount required for provider eligibility.", ge=Decimal("0")),
    ] = None,
    wait: Annotated[
        bool,
        Field(description="Wait for the job to reach a terminal state."),
    ] = False,
    timeout: Annotated[
        int | None,
        Field(description="Seconds to wait when --wait is used.", ge=1),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit an AI job via the aitbc CLI."""
    options: dict[str, str | None] = {"prompt": prompt, "currency": currency}
    if wallet is not None:
        options["wallet"] = wallet
    if job_type is not None:
        options["type"] = job_type
    if model is not None:
        options["model"] = model
    if payment is not None:
        options["payment"] = payment
    if offer_id is not None:
        options["offer-id"] = offer_id
    if min_reputation is not None:
        options["min-reputation"] = str(min_reputation)
    if buyer_address is not None:
        options["buyer-address"] = buyer_address
    if provider_address is not None:
        options["provider-address"] = provider_address
    if offer_quantity is not None:
        options["offer-quantity"] = offer_quantity
    if acceptance_window is not None:
        options["acceptance-window"] = str(acceptance_window)
    if zk_proof_required:
        options["zk-proof-required"] = None
    if tee_attestation_required:
        options["tee-attestation-required"] = None
    if tee_enclave_id is not None:
        options["tee-enclave-id"] = tee_enclave_id
    if confidential:
        options["confidential"] = None
    if enclave_measurement is not None:
        options["enclave-measurement"] = enclave_measurement
    if auto_reinvest_pct is not None:
        options["auto-reinvest-pct"] = str(auto_reinvest_pct)
    if bond_required:
        options["bond-required"] = None
    if min_bond_amount is not None:
        options["min-bond-amount"] = str(min_bond_amount)
    if wait:
        options["wait"] = None
    if timeout is not None:
        options["timeout"] = str(timeout)

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "submit", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", "submit", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def pay_for_ai_job(
    job_id: Annotated[
        str,
        Field(description="Job ID to pay for."),
    ],
    wallet: Annotated[
        str,
        Field(description="Wallet name to sign the escrow lock."),
    ],
    buyer_address: Annotated[
        str | None,
        Field(description="Override buyer/customer address."),
    ] = None,
    provider_address: Annotated[
        str | None,
        Field(description="Override provider address."),
    ] = None,
    currency: Annotated[
        str,
        Field(description="Payment currency."),
    ] = "AITBC",
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create an escrow payment for an existing job (two-step payment flow)."""
    options: dict[str, str | None] = {"job-id": job_id, "wallet": wallet, "currency": currency}
    if buyer_address is not None:
        options["buyer-address"] = buyer_address
    if provider_address is not None:
        options["provider-address"] = provider_address

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "pay", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", "pay", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def manage_ai_job(
    action: Annotated[
        Literal["accept", "cancel", "refund"],
        Field(description="Action to perform: accept a completed job, cancel a queued job, or refund a job."),
    ],
    job_id: Annotated[
        str,
        Field(description="Job ID to manage."),
    ],
    wallet: Annotated[
        str | None,
        Field(description="Wallet name (only used for cancel)."),
    ] = None,
    refund: Annotated[
        bool,
        Field(description="For cancel, also refund the escrowed payment."),
    ] = False,
    reason: Annotated[
        str,
        Field(description="Reason for cancel or refund."),
    ] = "buyer_requested",
    coordinator_url: Annotated[
        str | None,
        Field(description="Override coordinator URL."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Accept, cancel or refund an AI job through the aitbc CLI."""
    options: dict[str, str | None] = {"job-id": job_id}
    if action == "cancel" and wallet is not None:
        options["wallet"] = wallet
    if action == "cancel" and refund:
        options["refund"] = None
    if action in {"cancel", "refund"}:
        options["reason"] = reason
    if coordinator_url is not None:
        options["coordinator-url"] = coordinator_url

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", action, None, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", action, None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_zk_refund_sweep_candidates(
    limit: Annotated[
        int,
        Field(description="Maximum completed jobs to inspect.", ge=1),
    ] = 100,
    reason: Annotated[
        str,
        Field(description="Refund reason used for reporting."),
    ] = "buyer_requested",
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List completed jobs that the ZK refund sweep would refund (dry run)."""
    options: dict[str, str | None] = {"dry-run": None, "limit": str(limit), "reason": reason}
    target = _host_for_role(role, host)
    return _json(_run_aitbc_cli(target, "ai", "refund-sweep", None, options, "json", timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_zk_refund_sweep(
    limit: Annotated[
        int,
        Field(description="Maximum completed jobs to inspect.", ge=1),
    ] = 100,
    reason: Annotated[
        str,
        Field(description="Refund reason."),
    ] = "buyer_requested",
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run the client-side ZK refund sweep for failed ZK escrows."""
    options: dict[str, str | None] = {"limit": str(limit), "reason": reason}
    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "refund-sweep", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", "refund-sweep", None, options, "json", timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def send_aitbc_transaction(
    from_wallet: Annotated[
        str,
        Field(description="Source wallet name."),
    ],
    to_address: Annotated[
        str,
        Field(description="Destination address."),
    ],
    amount: Annotated[
        str,
        Field(description="Amount to send, e.g. '1.5'"),
    ],
    fee: Annotated[
        str | None,
        Field(description="Transaction fee."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Send AITBC from one wallet to another address."""
    options: dict[str, str | None] = {
        "from": from_wallet,
        "to": to_address,
        "amount": amount,
    }
    if fee is not None:
        options["fee"] = fee

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("transactions", "send", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "transactions", "send", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_performance_bond(
    provider_id: Annotated[
        str,
        Field(description="Provider ID or address."),
    ],
    amount: Annotated[
        str,
        Field(description="Amount to lock as a performance bond."),
    ],
    required_amount: Annotated[
        str | None,
        Field(description="Required bond amount for this provider."),
    ] = None,
    bond_id: Annotated[
        str | None,
        Field(description="Optional external bond identifier."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create or top up a provider's performance bond."""
    options: dict[str, str | None] = {"amount": amount}
    if required_amount is not None:
        options["required-amount"] = required_amount
    if bond_id is not None:
        options["bond-id"] = bond_id

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("bond", "create", [provider_id], options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "bond", "create", [provider_id], options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def stake_aitbc(
    amount: Annotated[
        str,
        Field(description="Amount to stake."),
    ],
    wallet_name: Annotated[
        str | None,
        Field(description="Wallet name to stake from."),
    ] = None,
    duration_days: Annotated[
        int | None,
        Field(description="Staking duration in days.", ge=1),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Stake AITBC tokens on the blockchain."""
    options: dict[str, str | None] = {}
    if wallet_name is not None:
        options["wallet-name"] = wallet_name
    if duration_days is not None:
        options["duration"] = str(duration_days)

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("wallet", "stake", [amount], options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "wallet", "stake", [amount], options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def unstake_aitbc(
    stake_id: Annotated[
        str,
        Field(description="Stake ID to unstake."),
    ],
    wallet_name: Annotated[
        str | None,
        Field(description="Wallet name to unstake from."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Unstake AITBC tokens from the blockchain."""
    options: dict[str, str | None] = {}
    if wallet_name is not None:
        options["wallet-name"] = wallet_name

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("wallet", "unstake", [stake_id], options, "json")
    guard = _require_confirm(dry_run, confirm, command)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "wallet", "unstake", [stake_id], options, "json"))


# ---------------------------------------------------------------------------
# Additional blockchain RPC router tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def query_blockchain_transactions(
    address: Annotated[
        str | None,
        Field(description="Filter by sender or recipient address."),
    ] = None,
    transaction_type: Annotated[
        str | None,
        Field(description="Filter by transaction type, e.g. 'TRANSFER', 'BRIDGE_LOCK', 'GPU_MARKETPLACE'."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status, e.g. 'confirmed', 'pending'."),
    ] = None,
    order_id: Annotated[
        str | None,
        Field(description="Filter by marketplace order ID."),
    ] = None,
    job_id: Annotated[
        str | None,
        Field(description="Filter by AI job ID."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Maximum number of transactions to return.", ge=1),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Query transactions on the blockchain RPC with optional filters."""
    params: dict[str, str] = {}
    if address is not None:
        params["address"] = address
    if transaction_type is not None:
        params["transaction_type"] = transaction_type
    if status is not None:
        params["status"] = status
    if order_id is not None:
        params["order_id"] = order_id
    if job_id is not None:
        params["job_id"] = job_id
    if limit is not None:
        params["limit"] = str(limit)
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", "transactions", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account_balance(
    address: Annotated[
        str,
        Field(description="Account address."),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get detailed balance breakdown for an account (available, staked, bridge locked)."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", f"balance/{address}", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def reconcile_account_balance(
    address: Annotated[
        str,
        Field(description="Account address."),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Reconcile account balance against all recorded operations."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", f"balance/{address}/reconcile", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account_state_snapshot(
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the full account state snapshot for follower sync."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", "state/snapshot", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account_state_delta(
    from_height: Annotated[
        int,
        Field(description="Start block height (inclusive).", ge=0),
    ],
    to_height: Annotated[
        int,
        Field(description="End block height (inclusive).", ge=0),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get state delta (changed accounts) between two block heights."""
    params: dict[str, str] = {
        "from_height": str(from_height),
        "to_height": str(to_height),
    }
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", "state/delta", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_genesis_allocations(
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get genesis allocations from the blockchain."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", "genesis_allocations", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_sync_config(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get sync optimization configuration."""
    return _http_read_tool(role, host, "blockchain-rpc", "sync/config")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_chains(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all chain instances running on the node."""
    return _http_read_tool(role, host, "blockchain-rpc", "chains")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_consensus_status(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get consensus status (mode, validator count, etc.)."""
    return _http_read_tool(role, host, "blockchain-rpc", "consensus/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_validators(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List consensus validators."""
    return _http_read_tool(role, host, "blockchain-rpc", "consensus/validators")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_staking_info(
    address: Annotated[
        str,
        Field(description="Account address."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get staking information for an address."""
    return _http_read_tool(role, host, "blockchain-rpc", f"staking/{address}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bond(
    bond_id: Annotated[
        str,
        Field(description="Bond ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a performance bond by ID."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bond/{bond_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_provider_bonds(
    provider: Annotated[
        str,
        Field(description="Provider ID or address."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List performance bonds for a provider."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bond/provider/{provider}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_transfer(
    transfer_id: Annotated[
        str,
        Field(description="Bridge transfer ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of a cross-chain bridge transfer."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/transfer/{transfer_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_pending_bridge_transfers(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List pending bridge transfers."""
    return _http_read_tool(role, host, "blockchain-rpc", "bridge/pending")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_rates(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get cross-chain exchange rates."""
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/rates")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_pools(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show cross-chain liquidity pools."""
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/pools")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_gpus(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all registered GPUs on the node."""
    return _http_read_tool(role, host, "blockchain-rpc", "gpus")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_gpu_info(
    gpu_id: Annotated[
        str,
        Field(description="GPU ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get GPU registration and status information."""
    return _http_read_tool(role, host, "blockchain-rpc", f"gpu/info/{gpu_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_ai_jobs_onchain(
    wallet_address: Annotated[
        str | None,
        Field(description="Filter by wallet address."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status."),
    ] = None,
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List AI jobs stored on the blockchain."""
    params: dict[str, str] = {}
    if wallet_address is not None:
        params["wallet_address"] = wallet_address
    if status is not None:
        params["status"] = status
    return _http_read_tool(role, host, "blockchain-rpc", "ai/jobs", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_job_onchain(
    job_id: Annotated[
        str,
        Field(description="AI job ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a single AI job from the blockchain by ID."""
    return _http_read_tool(role, host, "blockchain-rpc", f"ai/job/{job_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_escrow_state(
    job_id: Annotated[
        str,
        Field(description="Job ID for the escrow."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the escrow state for a job."""
    return _http_read_tool(role, host, "blockchain-rpc", f"escrow/{job_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_islands(
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all islands."""
    return _http_read_tool(role, host, "blockchain-rpc", "islands")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_island(
    island_id: Annotated[
        str,
        Field(description="Island ID."),
    ],
    role: Annotated[
        Literal["hub", "customer", "shop", "follower"] | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get details for a specific island."""
    return _http_read_tool(role, host, "blockchain-rpc", f"islands/{island_id}")


# ---------------------------------------------------------------------------
# Additional typed RPC tools from the companion module
# ---------------------------------------------------------------------------

import aitbc_mcp_rpc_tools  # noqa: F401  # registers more RPC tools


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
