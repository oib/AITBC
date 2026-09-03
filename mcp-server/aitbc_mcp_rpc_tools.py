"""Additional AITBC RPC router tools for the MCP server.

This module is imported by aitbc_mcp_server.py after the core helpers and
server are defined. It registers more read-only and mutating HTTP/RPC tools
without making the main file unmanageable.
"""

from __future__ import annotations

import json
import shlex
from decimal import Decimal

from typing import Annotated, Any

from mcp.types import ToolAnnotations

from pydantic import Field

from aitbc_mcp_server import (
    HTTP_SERVICE_NAMES,
    NodeRole,
    _build_dry_run,
    _host_for_role,
    _http_dry_run_command,
    _http_read_tool,
    _json,
    _run_http,
    mcp,
)


# ---------------------------------------------------------------------------
# HTTP write helper for mutating RPC calls
# ---------------------------------------------------------------------------


def _http_write_tool(
    role: str | None,
    host: str | None,
    service: str,
    path: str,
    body: dict[str, Any],
    dry_run: bool,
    confirm: bool,
    timeout: int = 120,
    auth: str = "none",
) -> str:
    """Run a mutating HTTP call with dry-run and confirmation gates via the CLI."""
    target = _host_for_role(role, host)
    if service not in HTTP_SERVICE_NAMES:
        return _json(
            {
                "error": f"unknown HTTP service: {service}",
                "known_services": sorted(HTTP_SERVICE_NAMES),
            }
        )

    command = _http_dry_run_command(service, path, "POST", None, body, auth)

    if dry_run:
        return _json(_build_dry_run("Set dry_run=false and confirm=true to execute.", command))
    if not confirm:
        return _json(
            {
                "error": "Confirmation required",
                "command": command,
                "note": "This is a destructive RPC call. Pass dry_run=false and confirm=true to execute.",
            }
        )

    return _json(_run_http(target, service, path, "POST", None, body, timeout, auth=auth))


# ---------------------------------------------------------------------------
# Mempool aliases
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_pending_mempool(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get pending transactions (alias endpoint)."""
    return _http_read_tool(role, host, "blockchain-rpc", "pending")


# ---------------------------------------------------------------------------
# Marketplace (on-chain)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_marketplace_listings(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List on-chain marketplace listings."""
    return _http_read_tool(role, host, "blockchain-rpc", "marketplace/listings")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_marketplace_listing(
    listing_id: Annotated[
        str,
        Field(description="Listing ID (typically tx_<id>)."),
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
    """Get a marketplace listing by ID."""
    return _http_read_tool(role, host, "blockchain-rpc", f"marketplace/listing/{listing_id}")


# ---------------------------------------------------------------------------
# Identity / governance
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_agent_identity(
    agent_id: Annotated[
        str,
        Field(description="Agent ID / wallet address."),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
    """Get a registered agent identity from the blockchain."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", f"identity/{agent_id}", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_governance_proposal(
    proposal_id: Annotated[
        str,
        Field(description="Governance proposal ID."),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
    """Get a governance proposal from the blockchain."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", f"governance/proposal/{proposal_id}", params)


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_transfer_proof(
    transfer_id: Annotated[
        str,
        Field(description="Bridge transfer ID."),
    ],
    source_chain: Annotated[
        str | None,
        Field(description="Source chain ID (defaults to this node)."),
    ] = None,
    block_height: Annotated[
        int | None,
        Field(description="Block height to anchor the proof.", ge=0),
    ] = None,
    block_hash: Annotated[
        str | None,
        Field(description="Block hash to anchor the proof."),
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
    """Build a Merkle proof for a locked bridge transfer."""
    params: dict[str, str] = {}
    if source_chain is not None:
        params["source_chain"] = source_chain
    if block_height is not None:
        params["block_height"] = str(block_height)
    if block_hash is not None:
        params["block_hash"] = block_hash
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/transfer/{transfer_id}/proof", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_balance(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
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
    """Get bridge balance for a chain."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/balance/{chain_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_validators(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
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
    """Get bridge validator set for a chain."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/validators/{chain_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_security_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get bridge security status."""
    return _http_read_tool(role, host, "blockchain-rpc", "bridge/security/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_oracle_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get bridge oracle/verification status."""
    return _http_read_tool(role, host, "blockchain-rpc", "bridge/oracle/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bridge_block_header(
    chain_id: Annotated[
        str,
        Field(description="Chain ID."),
    ],
    height: Annotated[
        int,
        Field(description="Block height.", ge=0),
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
    """Get a bridge block header with finality status."""
    return _http_read_tool(role, host, "blockchain-rpc", f"bridge/block-headers/{chain_id}/{height}")


# ---------------------------------------------------------------------------
# Cross-chain
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_cross_chain_swaps(
    user_address: Annotated[
        str | None,
        Field(description="Filter by user address."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status."),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Maximum number of swaps.", ge=1),
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
    """List cross-chain swaps with optional filters."""
    params: dict[str, str] = {}
    if user_address is not None:
        params["user_address"] = user_address
    if status is not None:
        params["status"] = status
    if limit is not None:
        params["limit"] = str(limit)
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/swaps", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_swap(
    swap_id: Annotated[
        str,
        Field(description="Swap ID."),
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
    """Get a cross-chain swap by ID."""
    return _http_read_tool(role, host, "blockchain-rpc", f"cross-chain/swap/{swap_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_bridge(
    bridge_id: Annotated[
        str,
        Field(description="Bridge transaction ID."),
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
    """Get cross-chain bridge transaction status."""
    return _http_read_tool(role, host, "blockchain-rpc", f"cross-chain/bridge/{bridge_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_cross_chain_stats(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show cross-chain trading statistics."""
    return _http_read_tool(role, host, "blockchain-rpc", "cross-chain/stats")


# ---------------------------------------------------------------------------
# ETH-AITBC bridge (wallet service)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the active ETH-AITBC bridge status and deposit address."""
    return _http_read_tool(role, host, "wallet", "v1/bridge/status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_deposit_instructions(
    eth_amount: Annotated[
        Decimal,
        Field(description="Amount of ETH to deposit.", gt=0),
    ],
    ait_address: Annotated[
        str,
        Field(description="AIT address that will receive minted AIT."),
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
    """Get ETH-AITBC bridge deposit instructions and AIT estimate."""
    body = {"eth_amount": str(eth_amount), "ait_address": ait_address}
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/deposit", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def eth_bridge_withdraw_estimate(
    ait_amount: Annotated[
        Decimal,
        Field(description="Amount of AIT to withdraw.", gt=0),
    ],
    eth_address: Annotated[
        str,
        Field(description="Destination Ethereum address."),
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
    """Estimate ETH payout for an AIT->ETH withdrawal."""
    body = {"ait_amount": str(ait_amount), "eth_address": eth_address}
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/withdraw/estimate", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def eth_bridge_withdraw_build(
    ait_amount: Annotated[
        Decimal,
        Field(description="Amount of AIT to withdraw.", gt=0),
    ],
    eth_address: Annotated[
        str,
        Field(description="Destination Ethereum address."),
    ],
    from_address: Annotated[
        str,
        Field(description="Source AIT address."),
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
    """Build an unsigned BRIDGE_WITHDRAW transaction for AIT->ETH."""
    body = {
        "ait_amount": str(ait_amount),
        "eth_address": eth_address,
        "from_address": from_address,
    }
    return _json(_run_http(_host_for_role(role, host), "wallet", "v1/bridge/withdraw/build", "POST", None, body))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def eth_bridge_withdraw_submit(
    signed_tx: Annotated[
        dict[str, Any],
        Field(description="Signed BRIDGE_WITHDRAW transaction object."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm execution of the destructive call."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit a signed BRIDGE_WITHDRAW transaction to the AITBC chain."""
    return _http_write_tool(role, host, "wallet", "v1/bridge/withdraw/submit", {"signed_tx": signed_tx}, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_eth_bridge_withdrawal(
    ait_tx_hash: Annotated[
        str,
        Field(description="AIT withdrawal transaction hash."),
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
    """Get the status of an AIT->ETH withdrawal."""
    return _http_read_tool(role, host, "wallet", f"v1/bridge/withdraw/{ait_tx_hash}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_eth_bridge_withdrawals(
    status: Annotated[
        str | None,
        Field(description="Filter by status (pending, completed, refunded, failed)."),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of withdrawals to return.", gt=0),
    ] = 50,
    offset: Annotated[
        int,
        Field(description="Number of withdrawals to skip.", ge=0),
    ] = 0,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List AIT->ETH withdrawals tracked by the bridge wallet."""
    params: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = status
    return _http_read_tool(role, host, "wallet", "v1/bridge/withdrawals", params)


# ---------------------------------------------------------------------------
# GPU resources (continued)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_gpu_allocations(
    gpu_id: Annotated[
        str,
        Field(description="GPU ID."),
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
    """Query GPU allocations."""
    return _http_read_tool(role, host, "blockchain-rpc", f"gpu/allocations/{gpu_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_edge_info(
    node_id: Annotated[
        str,
        Field(description="Edge node ID."),
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
    """Query an edge node registration."""
    return _http_read_tool(role, host, "blockchain-rpc", f"edge/info/{node_id}")


# ---------------------------------------------------------------------------
# AI services (on-chain)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_service_stats(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get AI service statistics from the blockchain."""
    return _http_read_tool(role, host, "blockchain-rpc", "ai/stats")


# ---------------------------------------------------------------------------
# Contracts / messaging / forum
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_contracts(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all deployed smart contracts."""
    return _http_read_tool(role, host, "blockchain-rpc", "contracts")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_messaging_contract_state(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the current state of the messaging contract."""
    return _http_read_tool(role, host, "blockchain-rpc", "contracts/messaging/state")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_forum_topics(
    limit: Annotated[
        int | None,
        Field(description="Maximum number of topics.", ge=1),
    ] = None,
    offset: Annotated[
        int | None,
        Field(description="Offset for pagination.", ge=0),
    ] = None,
    sort_by: Annotated[
        str | None,
        Field(description="Sort field, e.g. 'last_activity'."),
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
    """Get forum/messaging topics."""
    params: dict[str, str] = {}
    if limit is not None:
        params["limit"] = str(limit)
    if offset is not None:
        params["offset"] = str(offset)
    if sort_by is not None:
        params["sort_by"] = sort_by
    return _http_read_tool(role, host, "blockchain-rpc", "contracts/messaging/topics", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_topic_messages(
    topic_id: Annotated[
        str,
        Field(description="Topic ID."),
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
    """Get messages for a forum topic."""
    return _http_read_tool(role, host, "blockchain-rpc", f"contracts/messaging/topics/{topic_id}/messages")


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_active_disputes(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get all active disputes."""
    return _http_read_tool(role, host, "blockchain-rpc", "disputes/active")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_authorized_arbitrators(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get all authorized arbitrators."""
    return _http_read_tool(role, host, "blockchain-rpc", "disputes/arbitrators")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_arbitrator_disputes(
    arbitrator_address: Annotated[
        str,
        Field(description="Arbitrator address."),
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
    """Get disputes assigned to an arbitrator."""
    return _http_read_tool(role, host, "blockchain-rpc", f"disputes/arbitrators/{arbitrator_address}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_user_disputes(
    user_address: Annotated[
        str,
        Field(description="User address."),
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
    """Get all disputes for a specific user."""
    return _http_read_tool(role, host, "blockchain-rpc", f"disputes/user/{user_address}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_dispute(
    dispute_id: Annotated[
        int,
        Field(description="Dispute ID.", ge=0),
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
    """Get details of a specific dispute."""
    return _http_read_tool(role, host, "blockchain-rpc", f"disputes/{dispute_id}")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_dispute_evidence(
    dispute_id: Annotated[
        int,
        Field(description="Dispute ID.", ge=0),
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
    """Get evidence submitted for a dispute."""
    return _http_read_tool(role, host, "blockchain-rpc", f"disputes/{dispute_id}/evidence")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_arbitration_votes(
    dispute_id: Annotated[
        int,
        Field(description="Dispute ID.", ge=0),
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
    """Get arbitration votes for a dispute."""
    return _http_read_tool(role, host, "blockchain-rpc", f"disputes/{dispute_id}/votes")


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_subscribers(
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
    """Get all valid block subscribers."""
    params: dict[str, str] = {}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _http_read_tool(role, host, "blockchain-rpc", "subscribers", params)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_lease_status(
    node_id: Annotated[
        str,
        Field(description="Subscriber node ID."),
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
    """Get lease status for a block subscriber."""
    return _http_read_tool(role, host, "blockchain-rpc", f"lease/{node_id}")


# ---------------------------------------------------------------------------
# Mutating blockchain RPC tools (dry_run / confirm protected)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def submit_blockchain_transaction(
    transaction: Annotated[
        dict[str, Any],
        Field(description="Full transaction request object (sender, recipient, amount, fee, nonce, type, payload, sig)."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit a raw transaction to the blockchain mempool."""
    return _http_write_tool(role, host, "blockchain-rpc", "transaction", transaction, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def submit_marketplace_transaction(
    transaction: Annotated[
        dict[str, Any],
        Field(description="Marketplace transaction data."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit a marketplace transaction to the blockchain."""
    return _http_write_tool(role, host, "blockchain-rpc", "transactions/marketplace", transaction, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_marketplace_listing(
    seller_address: Annotated[
        str,
        Field(description="Seller wallet address."),
    ],
    item_type: Annotated[
        str,
        Field(description="Type of item, e.g. 'GPU'."),
    ],
    price: Annotated[
        Decimal,
        Field(description="Price in AIT.", ge=0),
    ],
    description: Annotated[
        str,
        Field(description="Item description."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a new on-chain marketplace listing."""
    body = {
        "seller_address": seller_address,
        "item_type": item_type,
        "price": price,
        "description": description,
    }
    return _http_write_tool(role, host, "blockchain-rpc", "marketplace/create", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def register_gpu(
    gpu_id: Annotated[
        str,
        Field(description="GPU unique identifier."),
    ],
    miner_id: Annotated[
        str,
        Field(description="Miner/provider ID."),
    ],
    model: Annotated[
        str,
        Field(description="GPU model."),
    ],
    memory_gb: Annotated[
        int,
        Field(description="GPU memory in GB.", ge=0),
    ],
    price_per_hour: Annotated[
        Decimal,
        Field(description="Price per hour in AIT.", ge=0),
    ],
    registered_by: Annotated[
        str,
        Field(description="Wallet address of registrant."),
    ],
    cuda_version: Annotated[
        str | None,
        Field(description="CUDA version."),
    ] = None,
    region: Annotated[
        str | None,
        Field(description="Geographic region."),
    ] = None,
    capabilities: Annotated[
        list[str] | None,
        Field(description="GPU capabilities, e.g. ['inference']"),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Register a GPU on the blockchain."""
    body: dict[str, Any] = {
        "gpu_id": gpu_id,
        "miner_id": miner_id,
        "model": model,
        "memory_gb": memory_gb,
        "price_per_hour": str(price_per_hour),
        "registered_by": registered_by,
    }
    if cuda_version is not None:
        body["cuda_version"] = cuda_version
    if region is not None:
        body["region"] = region
    if capabilities is not None:
        body["capabilities"] = capabilities
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "gpu/register", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def allocate_gpu(
    gpu_id: Annotated[
        str,
        Field(description="GPU ID to allocate."),
    ],
    client_id: Annotated[
        str,
        Field(description="Client wallet address."),
    ],
    duration_hours: Annotated[
        float,
        Field(description="Allocation duration in hours.", ge=0),
    ],
    total_cost: Annotated[
        Decimal,
        Field(description="Total cost in AIT.", ge=0),
    ],
    allocated_by: Annotated[
        str,
        Field(description="Wallet address of allocator."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Allocate a GPU on the blockchain."""
    body = {
        "gpu_id": gpu_id,
        "client_id": client_id,
        "duration_hours": duration_hours,
        "total_cost": str(total_cost),
        "allocated_by": allocated_by,
    }
    return _http_write_tool(role, host, "blockchain-rpc", "gpu/allocate", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def stake_tokens(
    address: Annotated[
        str,
        Field(description="Staker address."),
    ],
    amount: Annotated[
        int,
        Field(description="Amount to stake.", ge=1),
    ],
    signature: Annotated[
        str,
        Field(description="Staker signature authorizing the stake."),
    ],
    lock_days: Annotated[
        int,
        Field(description="Lock period in days.", ge=1),
    ] = 30,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Stake AITBC tokens for consensus participation."""
    body: dict[str, Any] = {
        "address": address,
        "amount": amount,
        "signature": signature,
        "lock_days": lock_days,
    }
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "staking/stake", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def unstake_tokens(
    address: Annotated[
        str,
        Field(description="Staker address."),
    ],
    stake_id: Annotated[
        str,
        Field(description="Stake ID to unstake."),
    ],
    signature: Annotated[
        str,
        Field(description="Staker signature authorizing the unstake."),
    ],
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Unstake AITBC tokens after the lock period expires."""
    body: dict[str, Any] = {
        "address": address,
        "stake_id": stake_id,
        "signature": signature,
    }
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "staking/unstake", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def register_agent_identity(
    agent_id: Annotated[
        str,
        Field(description="Agent ID."),
    ],
    agent_address: Annotated[
        str,
        Field(description="Agent wallet address."),
    ],
    display_name: Annotated[
        str | None,
        Field(description="Display name."),
    ] = None,
    agent_type: Annotated[
        str | None,
        Field(description="Agent type, e.g. 'general'."),
    ] = None,
    capabilities: Annotated[
        dict[str, Any] | None,
        Field(description="Agent capabilities object."),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Register an agent identity on the blockchain."""
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "agent_address": agent_address,
    }
    if display_name is not None:
        body["display_name"] = display_name
    if agent_type is not None:
        body["agent_type"] = agent_type
    if capabilities is not None:
        body["capabilities"] = capabilities
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "identity/register", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_governance_proposal(
    proposal_id: Annotated[
        str,
        Field(description="Unique proposal ID."),
    ],
    proposer_address: Annotated[
        str,
        Field(description="Proposer wallet address."),
    ],
    title: Annotated[
        str,
        Field(description="Proposal title."),
    ],
    description: Annotated[
        str | None,
        Field(description="Proposal description."),
    ] = None,
    category: Annotated[
        str | None,
        Field(description="Proposal category."),
    ] = None,
    voting_starts: Annotated[
        str | None,
        Field(description="ISO timestamp when voting starts."),
    ] = None,
    voting_ends: Annotated[
        str | None,
        Field(description="ISO timestamp when voting ends."),
    ] = None,
    execution_payload: Annotated[
        dict[str, Any] | None,
        Field(description="Execution payload object."),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a governance proposal on the blockchain."""
    body: dict[str, Any] = {
        "proposal_id": proposal_id,
        "proposer_address": proposer_address,
        "title": title,
    }
    if description is not None:
        body["description"] = description
    if category is not None:
        body["category"] = category
    if voting_starts is not None:
        body["voting_starts"] = voting_starts
    if voting_ends is not None:
        body["voting_ends"] = voting_ends
    if execution_payload is not None:
        body["execution_payload"] = execution_payload
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "governance/proposal", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def cast_governance_vote(
    proposal_id: Annotated[
        str,
        Field(description="Proposal ID."),
    ],
    voter_address: Annotated[
        str,
        Field(description="Voter wallet address."),
    ],
    vote_type: Annotated[
        str,
        Field(description="Vote type: 'for', 'against', or 'abstain'."),
    ] = "for",
    voting_power: Annotated[
        int,
        Field(description="Voting power.", ge=0),
    ] = 0,
    reason: Annotated[
        str | None,
        Field(description="Optional reason."),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Cast a vote on a governance proposal."""
    body: dict[str, Any] = {
        "proposal_id": proposal_id,
        "voter_address": voter_address,
        "vote_type": vote_type,
        "voting_power": voting_power,
    }
    if reason is not None:
        body["reason"] = reason
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "governance/vote", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def execute_governance_proposal(
    proposal_id: Annotated[
        str,
        Field(description="Proposal ID to execute."),
    ],
    executor_address: Annotated[
        str | None,
        Field(description="Executor address (defaults to node governance key)."),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Execute a passed governance proposal on the blockchain."""
    body: dict[str, Any] = {}
    if executor_address is not None:
        body["executor_address"] = executor_address
    if chain_id is not None:
        body["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", f"governance/proposal/{proposal_id}/execute", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_cross_chain_swap(
    from_chain: Annotated[
        str,
        Field(description="Source chain ID."),
    ],
    to_chain: Annotated[
        str,
        Field(description="Target chain ID."),
    ],
    from_token: Annotated[
        str,
        Field(description="Source token."),
    ],
    to_token: Annotated[
        str,
        Field(description="Target token."),
    ],
    amount: Annotated[
        Decimal,
        Field(description="Amount to swap.", gt=0),
    ],
    user_address: Annotated[
        str | None,
        Field(description="User address."),
    ] = None,
    slippage_tolerance: Annotated[
        float,
        Field(description="Slippage tolerance.", ge=0, le=1),
    ] = 0.01,
    min_amount: Annotated[
        Decimal | None,
        Field(description="Minimum acceptable output amount."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a cross-chain swap."""
    body: dict[str, Any] = {
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "amount": amount,
        "slippage_tolerance": slippage_tolerance,
    }
    if user_address is not None:
        body["user_address"] = user_address
    if min_amount is not None:
        body["min_amount"] = min_amount
    return _http_write_tool(role, host, "blockchain-rpc", "cross-chain/swap", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_cross_chain_bridge(
    source_chain: Annotated[
        str,
        Field(description="Source chain ID."),
    ],
    target_chain: Annotated[
        str,
        Field(description="Target chain ID."),
    ],
    token: Annotated[
        str,
        Field(description="Token identifier."),
    ],
    amount: Annotated[
        Decimal,
        Field(description="Amount to bridge.", gt=0),
    ],
    recipient_address: Annotated[
        str,
        Field(description="Recipient address."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a cross-chain bridge transaction."""
    body = {
        "source_chain": source_chain,
        "target_chain": target_chain,
        "token": token,
        "amount": amount,
        "recipient_address": recipient_address,
    }
    return _http_write_tool(role, host, "blockchain-rpc", "cross-chain/bridge", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def bridge_lock(
    target_chain: Annotated[
        str,
        Field(description="Target chain ID."),
    ],
    sender: Annotated[
        str,
        Field(description="Sender address."),
    ],
    recipient: Annotated[
        str,
        Field(description="Recipient address."),
    ],
    amount: Annotated[
        int,
        Field(description="Amount to bridge.", gt=0),
    ],
    signature: Annotated[
        str,
        Field(description="Sender signature authorizing the lock."),
    ],
    asset: Annotated[
        str | None,
        Field(description="Asset identifier."),
    ] = "native",
    source_chain: Annotated[
        str | None,
        Field(description="Source chain ID (defaults to this chain)."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Lock funds for a cross-chain bridge transfer."""
    body: dict[str, Any] = {
        "target_chain": target_chain,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "signature": signature,
        "asset": asset or "native",
    }
    if source_chain is not None:
        body["source_chain"] = source_chain
    return _http_write_tool(role, host, "blockchain-rpc", "bridge/lock", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def bridge_confirm(
    transfer_id: Annotated[
        str,
        Field(description="Transfer ID to confirm."),
    ],
    proof: Annotated[
        str | dict[str, Any],
        Field(description="Merkle proof of the lock (string or dict)."),
    ],
    signature: Annotated[
        str,
        Field(description="Confirmer signature."),
    ],
    confirmer: Annotated[
        str | None,
        Field(description="Confirmer address (defaults to recipient)."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Confirm and release a cross-chain bridge transfer."""
    body: dict[str, Any] = {
        "transfer_id": transfer_id,
        "proof": proof,
        "signature": signature,
    }
    if confirmer is not None:
        body["confirmer"] = confirmer
    return _http_write_tool(role, host, "blockchain-rpc", "bridge/confirm", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def bridge_unlock(
    transfer_id: Annotated[
        str,
        Field(description="Transfer ID to refund."),
    ],
    sender: Annotated[
        str,
        Field(description="Original sender address."),
    ],
    signature: Annotated[
        str,
        Field(description="Sender signature authorizing the refund."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Refund/cancel a pending bridge transfer and return locked funds."""
    body = {
        "transfer_id": transfer_id,
        "sender": sender,
        "signature": signature,
    }
    return _http_write_tool(role, host, "blockchain-rpc", "bridge/unlock", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_escrow(
    job_id: Annotated[
        str,
        Field(description="Job ID."),
    ],
    buyer: Annotated[
        str,
        Field(description="Buyer wallet address."),
    ],
    provider: Annotated[
        str,
        Field(description="Provider wallet address."),
    ],
    amount: Annotated[
        Decimal,
        Field(description="Escrow amount in AIT.", gt=0),
    ],
    lock_signature: Annotated[
        str | None,
        Field(description="Signature for the lock transaction."),
    ] = None,
    lock_tx: Annotated[
        dict[str, Any] | None,
        Field(description="Fully signed lock transaction object."),
    ] = None,
    lock_nonce: Annotated[
        int | None,
        Field(description="Lock transaction nonce."),
    ] = None,
    lock_fee: Annotated[
        int | None,
        Field(description="Lock transaction fee."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create a new escrow contract after the buyer has signed an ESCROW_LOCK transaction."""
    body: dict[str, Any] = {
        "job_id": job_id,
        "buyer": buyer,
        "provider": provider,
        "amount": amount,
    }
    if lock_tx is not None:
        body["lock_tx"] = lock_tx
    if lock_signature is not None:
        body["lock_signature"] = lock_signature
    if lock_nonce is not None:
        body["lock_nonce"] = lock_nonce
    if lock_fee is not None:
        body["lock_fee"] = lock_fee
    return _http_write_tool(role, host, "blockchain-rpc", "escrow/create", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def release_escrow(
    job_id: Annotated[
        str,
        Field(description="Job ID."),
    ],
    job_tx_hash: Annotated[
        str | None,
        Field(description="Optional job transaction hash as proof of work reference."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Release escrow funds to the provider."""
    body: dict[str, Any] = {}
    if job_tx_hash is not None:
        body["job_tx_hash"] = job_tx_hash
    return _http_write_tool(role, host, "blockchain-rpc", f"escrow/{job_id}/release", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def refund_escrow(
    job_id: Annotated[
        str,
        Field(description="Job ID."),
    ],
    reason: Annotated[
        str | None,
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Refund escrow to the buyer."""
    body = {"reason": reason or "buyer_requested"}
    return _http_write_tool(role, host, "blockchain-rpc", f"escrow/{job_id}/refund", body, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def register_account(
    account_data: Annotated[
        dict[str, Any],
        Field(description="Account registration data."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create/register a new account on the blockchain."""
    return _http_write_tool(role, host, "blockchain-rpc", "register-account", account_data, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def request_faucet(
    address: Annotated[
        str,
        Field(description="Wallet address to fund."),
    ],
    amount: Annotated[
        int | None,
        Field(description="Amount to fund; defaults to the faucet’s default."),
    ] = None,
    chain_id: Annotated[
        str | None,
        Field(description="Chain ID override."),
    ] = None,
    faucet_data: Annotated[
        dict[str, Any] | None,
        Field(description="Raw faucet request payload (overrides the explicit fields)."),
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
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Request test tokens from the blockchain faucet."""
    if faucet_data is None:
        faucet_data = {"address": address}
        if amount is not None:
            faucet_data["amount"] = amount
        if chain_id is not None:
            faucet_data["chain_id"] = chain_id
    return _http_write_tool(role, host, "blockchain-rpc", "faucet", faucet_data, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def force_sync_chain(
    peer_data: Annotated[
        dict[str, Any],
        Field(description="Force sync peer data (peer_url, target_height, etc.)."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Force blockchain reorganization to sync with a specified peer."""
    return _http_write_tool(role, host, "blockchain-rpc", "force-sync", peer_data, dry_run, confirm)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ipfs_rental_token(
    access_key: Annotated[
        str,
        Field(description="The rental access key (public identifier)."),
    ],
    access_secret: Annotated[
        str,
        Field(description="The rental access secret."),
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
    """Validate an IPFS rental access token and return its CID and metadata."""
    return _http_read_tool(
        role,
        host,
        "marketplace",
        f"v1/marketplace/ipfs/rental/{access_key}",
        {"access_secret": access_secret},
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def register_ipfs_rental_token(
    token: Annotated[
        dict[str, Any],
        Field(
            description="IPFS rental token data (access_key, access_secret, rental_id, offer_id, cid, buyer_address, provider_address, escrow_contract_id, status, expires_at, disk_quota_mb, size, ipfs_api, public_endpoint)."
        ),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to submit to."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Register an IPFS rental access token with the marketplace service."""
    return _http_write_tool(
        role,
        host,
        "marketplace",
        "v1/marketplace/ipfs/rental-token",
        token,
        dry_run,
        confirm,
    )
