"""Destructive node-control MCP tools, dry-run by default (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    AITBC_CLI,
    NodeRole,
    _build_aitbc_cli_command,
    _host_for_role,
    _json,
    _require_confirm,
    _run_aitbc_cli,
    _run_remote,
    _safe_command,
    mcp,
)

# ---------------------------------------------------------------------------
# Destructive tools (dry-run by default)
# ---------------------------------------------------------------------------


def _control_node(
    action: str,
    role: NodeRole,
    dry_run: bool,
    confirm: bool,
    host: str | None = None,
) -> str:
    """Start, stop, or restart all role services on a node."""
    target = _host_for_role(role, host)
    real_command = f"sudo -n {AITBC_CLI} {action} --role {role}"
    guard = _require_confirm(dry_run, confirm, real_command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_remote(target, real_command, timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def start_node(
    role: Annotated[
        NodeRole,
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
        NodeRole,
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
        NodeRole,
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
        NodeRole,
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
    if ".." in Path(script_path).parts or not script_path.startswith("/"):
        return _json({"error": "invalid script path", "path": script_path})
    command = _build_aitbc_cli_command(
        "system",
        "run-script",
        [],
        {"path": script_path},
        output_format="json",
    )
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)

    return _json(_run_aitbc_cli(target, "system", "run-script", [], {"path": script_path}, output_format="json", timeout=300))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_aitbc_command(
    role: Annotated[
        NodeRole,
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
    - ``blockchain status``
    - ``wallet list``
    - ``market list``
    - ``ai jobs``
    - ``zk health``
    """
    ok, tokens = _safe_command(command)
    if not ok:
        return _json({"error": "invalid command", "details": tokens})

    target = _host_for_role(role, host)
    quoted = " ".join(shlex.quote(t) for t in tokens)
    real_command = f"{AITBC_CLI} {quoted}"
    guard = _require_confirm(dry_run, confirm, real_command, host=target)
    if guard is not None:
        return _json(guard)

    return _json(_run_remote(target, real_command, timeout=120))


# ---------------------------------------------------------------------------
