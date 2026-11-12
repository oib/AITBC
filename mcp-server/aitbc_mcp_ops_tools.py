"""Phase-6 daily-use CLI wrapper MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    NodeRole,
    _aitbc_cli_read_tool,
    mcp,
)

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
        NodeRole | None,
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
def list_aitbc_ipfs_pins(
    role: Annotated[
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the shop dashboard with live balances and market offers."""
    return _aitbc_cli_read_tool(role, host, "dashboard", "shop")


# ---------------------------------------------------------------------------
