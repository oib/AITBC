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
from typing import Annotated, Any, Literal

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
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
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
    "aitbc-monitoring": "http://localhost:8002/health",
}


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
    return _json({
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
        "note": (
            "Connections use passwordless SSH. "
            "Set AITBC_MCP_SSH_USER and AITBC_MCP_DEFAULT_HOST in the MCP env."
        ),
    })


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
            f"[ -n \"$state\" ] || state=unknown; "
            f"props=$(systemctl show {service} --property=ActiveState,SubState,LoadState,MainPID 2>/dev/null); "
            f"printf \"%s\\t%s\\n%s\\n\" \"{service}\" \"$state\" \"$props\"'"
        )
    else:
        command = (
            "bash -c 'source /opt/aitbc/scripts/monitoring/health_check.sh >/dev/null 2>&1; "
            "for svc in ${ROLE_SERVICES[@]}; do "
            "state=$(systemctl is-active $svc 2>/dev/null || true); "
            "[ -n \"$state\" ] || state=unknown; "
            "printf \"%s\\t%s\\n\" \"$svc\" \"$state\"; "
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
        "  [ -z \"$url\" ] && continue; "
        "  code=$(curl -sf -o /dev/null -w \"%{http_code}\" \"$url\" 2>/dev/null || true); [ -z \"$code\" ] && code=000; "
        "  printf \"%s\\t%s\\n\" \"$svc\" \"$code\"; "
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
        "bash -c 'echo \"=== service status ===\"; "
        "systemctl is-active aitbc-blockchain-event-bridge 2>/dev/null || true; "
        "echo \"=== bridge metrics ===\"; "
        "curl -sfL http://localhost:8205/metrics/ 2>/dev/null | grep -E \"^bridge_(actions|events)_\" | head -50'"
    )
    return _json(_run_remote(target, command, timeout=20))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_rebalance_triggers() -> str:
    """List the agent/economic rebalancing trigger types and action types."""
    return _json({
        "rebalancing_triggers": ["threshold", "schedule", "opportunity"],
        "rebalance_action_types": ["buy", "sell", "transfer", "stake", "reinvest", "hold"],
        "constraint_types": ["max_exposure", "min_liquidity", "diversification", "min_reinvest_amount"],
        "note": (
            "For a concrete rebalance plan, fetch an agent's holdings and "
            "ReinvestmentPolicy from the coordinator API or wallet and use the "
            "Rebalancer class in aitbc.agent_economics.rebalance."
        ),
    })


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
        "bash -c 'echo \"=== user crontab ===\"; "
        "(crontab -l 2>/dev/null) || echo \"no user crontab\"; "
        "echo \"=== /etc/cron.d ===\"; "
        "ls -1 /etc/cron.d/aitbc* 2>/dev/null || true; "
        "for f in /etc/cron.d/aitbc*; do "
        "  [ -f \"$f\" ] || continue; "
        "  echo \"--- $f ---\"; "
        "  cat \"$f\"; "
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
        return _json({
            "error": "script path not allowed",
            "path": script_path,
            "allowed_prefixes": ALLOWED_SCRIPT_PREFIXES,
        })

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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
