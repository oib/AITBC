"""Blockchain RPC router MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    NodeRole,
    _aitbc_cli_read_tool,
    _http_read_tool,
    mcp,
)

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
        Field(description="Filter by transaction type, e.g. 'TRANSFER', 'BRIDGE_LOCK', 'GPU_MARKET'."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status, e.g. 'confirmed', 'pending'."),
    ] = None,
    order_id: Annotated[
        str | None,
        Field(description="Filter by market order ID."),
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List all registered GPUs on the node via the local gpu-service."""
    return _aitbc_cli_read_tool(role, host, "gpu", "list-gpus")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_gpu_info(
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
    """Get GPU registration and status information from the local gpu-service."""
    return _http_read_tool(role, host, "gpu", f"v1/gpu/{gpu_id}")


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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
        NodeRole | None,
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
