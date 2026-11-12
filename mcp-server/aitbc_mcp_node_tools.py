"""Read-only node/chain inspection MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    NodeRole,
    _ROLE_SITES,
    _default_host,
    _execution_context,
    _host_for_role,
    _json,
    _role_hosts,
    _run_aitbc_cli,
    _ssh_user,
    mcp,
)

# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_nodes() -> str:
    """List the AITBC nodes and roles this MCP server can reach."""
    roles = _role_hosts()
    return _json(
        {
            "nodes": [
                {"role": role, **_execution_context(host), "site": _ROLE_SITES.get(role, "live node")}
                for role, host in roles.items()
            ],
            "environment": {
                "default_host": _default_host(),
                "ssh_user": _ssh_user() or "(current user)",
            },
            "note": (
                "Connections use passwordless SSH. Configure roles with AITBC_MCP_HOSTS or an mcp-hosts.{yaml,json} file."
            ),
        }
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def node_status(
    role: Annotated[
        NodeRole | None,
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
    options: dict[str, str | None] = {}
    if service:
        options["service"] = service
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "check",
            [],
            options,
            output_format="json",
            timeout=60,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_service_health(
    role: Annotated[
        NodeRole | None,
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
    """Query the active/reachable state of AITBC services."""
    target = _host_for_role(role, host)
    options: dict[str, str | None] = {}
    if service:
        options["service"] = service
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "check",
            [],
            options,
            output_format="json",
            timeout=60,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_chain_height(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current blockchain height from the node's RPC."""
    target = _host_for_role(role, host)
    return _json(_run_aitbc_cli(target, "blockchain", "height", [], {}, output_format="json", timeout=30))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_block(
    height: Annotated[
        int,
        Field(description="Block height to retrieve.", ge=0),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get a block by height from the node's RPC."""
    target = _host_for_role(role, host)
    return _json(
        _run_aitbc_cli(
            target,
            "blockchain",
            "block",
            [],
            {"height": str(height)},
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_trigger_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get blockchain event bridge trigger and action metrics."""
    target = _host_for_role(role, host)
    return _json(_run_aitbc_cli(target, "bridge", "status", [], {}, output_format="json", timeout=30))


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
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List cron jobs for the AITBC user and /etc/cron.d entries."""
    target = _host_for_role(role, host)
    return _json(_run_aitbc_cli(target, "system", "cron", [], {}, output_format="json", timeout=30))


# ---------------------------------------------------------------------------
